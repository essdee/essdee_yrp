<template>
	<DepartmentPage title="Layout Builder" full-width>
		<div class="layout-builder">
			<header class="layout-builder__toolbar">
				<Select
					v-model="selectedName"
					:options="layoutOptions"
					option-label="label"
					option-value="value"
					placeholder="Open a layout"
					class="layout-builder__picker"
					aria-label="Open a layout"
					:loading="loading"
					show-clear
					@change="openLayout($event.value)"
				/>
				<Button label="New layout" icon="pi pi-plus" severity="secondary" outlined @click="openLayout('')" />
				<span class="layout-builder__spacer" />
				<Button :label="previewing ? 'Edit' : 'Preview'" :icon="previewing ? 'pi pi-pencil' : 'pi pi-eye'" severity="secondary" outlined @click="previewing = !previewing" />
				<Button v-if="draft.originalName && !draft.department" label="Delete" icon="pi pi-trash" severity="danger" outlined :disabled="saving" @click="confirmDelete" />
				<Button v-if="draft.department && draft.hasOverride" label="Reset to default" icon="pi pi-undo" severity="danger" outlined :disabled="saving" @click="confirmReset" />
				<Button label="Save" icon="pi pi-check" :loading="saving" :disabled="problems.length > 0" @click="save" />
			</header>

			<Message v-if="loadError" severity="error" :closable="false">{{ loadError }}</Message>
			<Message v-if="problems.length && !previewing" severity="secondary" :closable="false">
				<ul class="layout-builder__problems"><li v-for="problem in problems" :key="problem">{{ problem }}</li></ul>
			</Message>
			<p v-if="draft.department" class="layout-builder__hint">Built-in layout: saving replaces the {{ draft.title }} landing page cards for everyone who opens it; its users see the change after reload.</p>
			<p v-else class="layout-builder__hint">Saved layouts appear in YRP UI Preference. Assign one to a user there to give them this workspace.</p>

			<WorkspaceLauncher v-if="previewing" :title="draft.title || 'Untitled layout'" eyebrow="Preview" :sections="previewSections" compact empty-text="Add cards to see the preview" />

			<div v-else class="layout-builder__columns">
				<aside class="layout-builder__catalogue erp-card" aria-labelledby="layout-builder-catalogue-title">
					<h2 id="layout-builder-catalogue-title">Cards</h2>
					<InputText v-model="query" placeholder="Search cards" aria-label="Search cards" class="layout-builder__search" />
					<section v-for="group in catalogueGroups" :key="group.department.key" class="layout-builder__group">
						<h3>{{ group.department.label }}</h3>
						<div
							v-for="entry in group.entries"
							:key="entry.id"
							class="layout-builder__entry"
							:class="{ 'is-placed': entry.placed }"
							draggable="true"
							@dragstart="startDrag($event, { id: entry.id })"
							@dragend="drag = null"
						>
							<i :class="entry.card.icon" aria-hidden="true" />
							<span>{{ entry.card.label }}</span>
							<Button
								icon="pi pi-plus"
								severity="secondary"
								text
								rounded
								size="small"
								:disabled="entry.placed || !draft.sections.length"
								:aria-label="`Add ${entry.label}`"
								@click="addCard(draft, draft.sections.length - 1, entry.id)"
							/>
						</div>
					</section>
					<p v-if="!catalogueGroups.length" class="layout-builder__empty">No cards match.</p>
				</aside>

				<section class="layout-builder__layout" aria-label="Layout">
					<label class="layout-builder__title">
						<span>Layout title</span>
						<InputText v-model="draft.title" placeholder="e.g. Merch Desk" :disabled="Boolean(draft.department)" />
					</label>
					<section v-for="(section, sectionIndex) in draft.sections" :key="section.key" class="layout-builder__section erp-card">
						<header>
							<InputText v-model="section.label" :aria-label="`Section ${sectionIndex + 1} name`" placeholder="Section name" />
							<Button icon="pi pi-trash" severity="secondary" text rounded :aria-label="`Delete section ${section.label}`" @click="removeSection(draft, sectionIndex)" />
						</header>
						<ol class="layout-builder__cards" @dragover.prevent @drop.prevent="drop(sectionIndex, section.cards.length)">
							<li
								v-for="(id, cardIndex) in section.cards"
								:key="id"
								class="layout-builder__card"
								draggable="true"
								@dragstart="startDrag($event, { section: sectionIndex, index: cardIndex })"
								@dragover.prevent.stop
								@drop.prevent.stop="drop(sectionIndex, cardIndex)"
								@dragend="drag = null"
							>
								<i class="pi pi-bars layout-builder__handle" aria-hidden="true" />
								<span>{{ cardLabel(id) }}</span>
								<Button icon="pi pi-arrow-up" severity="secondary" text rounded size="small" :aria-label="`Move ${cardLabel(id)} up`" @click="moveCardBy(draft, sectionIndex, cardIndex, -1)" />
								<Button icon="pi pi-arrow-down" severity="secondary" text rounded size="small" :aria-label="`Move ${cardLabel(id)} down`" @click="moveCardBy(draft, sectionIndex, cardIndex, 1)" />
								<Button icon="pi pi-times" severity="secondary" text rounded size="small" :aria-label="`Remove ${cardLabel(id)}`" @click="removeCard(draft, sectionIndex, cardIndex)" />
							</li>
							<li v-if="!section.cards.length" class="layout-builder__drop">Drag cards here</li>
						</ol>
					</section>
					<Button label="Add section" icon="pi pi-plus" severity="secondary" outlined @click="addSection(draft)" />
				</section>
			</div>
		</div>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"
import { useToast } from "primevue/usetoast"
import { computed, onMounted, reactive, ref } from "vue"

import { deleteLayout, getBuilderData, resetDepartmentOverride, saveDepartmentOverride, saveLayout } from "../../api/workspaceLayout.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLauncher from "../../components/common/WorkspaceLauncher.vue"
import { useActionConfirmation } from "../../utils/useActionConfirmation.js"
import { getCatalogueCard } from "../cardCatalogue.js"
import { toLauncherCard } from "./workspaceSections.js"
import { addCard, addSection, createDepartmentDraft, createDraft, getCatalogueGroups, getDraftProblems, getPayload, moveCard, moveCardBy, removeCard, removeSection } from "./layoutBuilder.js"

const toast = useToast()
const confirmAction = useActionConfirmation()
const loading = ref(true)
const loadError = ref("")
const saving = ref(false)
const previewing = ref(false)
const layouts = ref([])
const departmentLayouts = ref([])
const reservedNames = ref([])
const selectedName = ref("")
const query = ref("")
const draft = reactive(createDraft())
const drag = ref(null)

const layoutOptions = computed(() => [
	...layouts.value.map((layout) => ({ label: layout.name, value: layout.name })),
	...departmentLayouts.value.map((layout) => ({ label: `${layout.name} (built-in)`, value: layout.name })),
])
const placed = computed(() => new Set(draft.sections.flatMap((section) => section.cards)))
const catalogueGroups = computed(() => getCatalogueGroups(query.value, placed.value))
const problems = computed(() => getDraftProblems(draft, reservedNames.value))
const previewSections = computed(() => draft.sections.map((section) => ({
	label: section.label,
	items: section.cards.map(getCatalogueCard).filter(Boolean).map(toLauncherCard),
})))
const cardLabel = (id) => getCatalogueCard(id)?.label || id

const showError = (reason) => toast.add({ severity: "error", summary: reason?.message || "The layout could not be changed.", life: 6000 })

function openLayout(name) {
	selectedName.value = name || ""
	const department = departmentLayouts.value.find((layout) => layout.name === name)
	Object.assign(draft, department ? createDepartmentDraft(department) : createDraft(layouts.value.find((layout) => layout.name === name) || null))
	previewing.value = false
}

function startDrag(event, source) {
	drag.value = source
	event.dataTransfer.effectAllowed = "move"
	event.dataTransfer.setData("text/plain", source.id || "")
}

function drop(section, index) {
	const source = drag.value
	drag.value = null
	if (!source) return
	if (source.id) addCard(draft, section, source.id, index)
	else moveCard(draft, source, { section, index })
}

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		const data = await getBuilderData()
		layouts.value = data?.layouts || []
		departmentLayouts.value = data?.department_layouts || []
		reservedNames.value = data?.reserved_names || []
	} catch (reason) {
		loadError.value = reason?.message || "Unable to load builder layouts."
	} finally {
		loading.value = false
	}
}

async function save() {
	saving.value = true
	try {
		const { name } = await (draft.department ? saveDepartmentOverride : saveLayout)(getPayload(draft))
		await load()
		openLayout(name)
		toast.add({ severity: "success", summary: `Saved ${name}`, life: 3000 })
	} catch (reason) {
		showError(reason)
	} finally {
		saving.value = false
	}
}

/** Asks first, then runs `change` on the open layout and reopens `reopen` after reloading. */
function confirmChange({ header, message, acceptLabel, rejectLabel, change, reopen, summary }) {
	confirmAction({
		header,
		message,
		acceptLabel,
		rejectLabel,
		accept: async () => {
			saving.value = true
			try {
				await change()
				await load()
				openLayout(reopen)
				toast.add({ severity: "success", summary, life: 3000 })
			} catch (reason) {
				showError(reason)
			} finally {
				saving.value = false
			}
		},
	})
}

function confirmDelete() {
	const name = draft.originalName
	confirmChange({
		header: "Delete layout?",
		message: `${name} will be removed. Users whose YRP UI Preference uses it must be moved to another layout first.`,
		acceptLabel: "Delete",
		rejectLabel: "Keep Layout",
		change: () => deleteLayout(name),
		reopen: "",
		summary: `Deleted ${name}`,
	})
}

function confirmReset() {
	const name = draft.originalName
	confirmChange({
		header: "Reset to default?",
		message: `${name} will show its built-in cards again for everyone.`,
		acceptLabel: "Reset",
		rejectLabel: "Keep Changes",
		change: () => resetDepartmentOverride(name),
		reopen: name,
		summary: `Reset ${name}`,
	})
}

onMounted(load)
</script>

<style scoped>
.layout-builder { display: grid; gap: var(--erp-space-3); }
.layout-builder__toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: var(--erp-space-2); }
.layout-builder__picker { width: min(320px, 100%); }
.layout-builder__spacer { flex: 1; }
.layout-builder__problems { margin: 0; padding-left: var(--erp-space-4); }
.layout-builder__hint { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.layout-builder__columns { display: grid; grid-template-columns: minmax(260px, 340px) minmax(0, 1fr); gap: var(--erp-space-4); align-items: start; }
.layout-builder__catalogue { display: grid; gap: var(--erp-space-2); max-height: calc(100vh - 220px); overflow: auto; padding: var(--erp-space-3); }
.layout-builder__catalogue h2 { margin: 0; font-size: var(--erp-font-size-section); }
.layout-builder__search { width: 100%; }
.layout-builder__group h3 { margin: var(--erp-space-2) 0 var(--erp-space-1); color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); text-transform: uppercase; letter-spacing: .05em; }
.layout-builder__entry, .layout-builder__card { display: flex; align-items: center; gap: var(--erp-space-2); min-height: 36px; padding: 2px var(--erp-space-2); border: 1px solid var(--erp-border); border-radius: 8px; background: var(--erp-surface); cursor: grab; }
.layout-builder__entry + .layout-builder__entry { margin-top: var(--erp-space-1); }
.layout-builder__entry span, .layout-builder__card span { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.layout-builder__entry.is-placed { opacity: .55; }
.layout-builder__layout { display: grid; gap: var(--erp-space-3); align-content: start; }
.layout-builder__title { display: grid; gap: var(--erp-space-1); max-width: 420px; font-weight: var(--erp-font-weight-semibold); }
.layout-builder__section { display: grid; gap: var(--erp-space-2); padding: var(--erp-space-3); }
.layout-builder__section header { display: flex; align-items: center; gap: var(--erp-space-2); }
.layout-builder__section header .p-inputtext { flex: 1; font-weight: var(--erp-font-weight-semibold); }
.layout-builder__cards { display: grid; gap: var(--erp-space-1); min-height: 44px; margin: 0; padding: 0; list-style: none; }
.layout-builder__handle { color: var(--erp-text-subtle); }
.layout-builder__drop { display: grid; min-height: 44px; place-items: center; color: var(--erp-text-muted); border: 1px dashed var(--erp-border); border-radius: 8px; }
@media (max-width: 820px) {
	.layout-builder__columns { grid-template-columns: 1fr; }
	.layout-builder__catalogue { max-height: 320px; }
}
</style>
