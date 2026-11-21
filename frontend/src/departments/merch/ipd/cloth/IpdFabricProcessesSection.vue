<template>
	<IpdSection :section-key="sectionKey">
		<div ref="root" class="ipd-cloth-stack ipd-fp">
			<p v-if="!steps.length" class="erp-empty-state erp-empty-state--compact ipd-cloth-empty">No fabric processes yet.</p>
			<ol v-else class="ipd-fp-cards" aria-label="Fabric processes">
				<li v-for="(step, index) in steps" :key="step.key" class="ipd-fp-card" :class="`ipd-fp-card--${shapeOf(step).key}`" :data-fp-key="step.key" data-testid="fp-card">
					<span class="ipd-fp-seq">{{ index + 1 }}</span>
					<div class="ipd-fp-card__head">
						<span class="ipd-fp-name">{{ step.fabric_process || "(no process)" }}</span>
						<span class="ipd-fp-badge" :class="`ipd-fp-badge--${shapeOf(step).key}`">{{ shapeOf(step).label }}</span>
						<div v-if="!readonly" class="ipd-fp-actions">
							<Button icon="pi pi-arrow-up" text severity="secondary" size="small" data-testid="fp-move-up" :aria-label="`Move ${step.fabric_process} up`" title="Move process up" :disabled="!canMoveProcess(processes, index, -1)" @click="move(index, -1)" />
							<Button icon="pi pi-arrow-down" text severity="secondary" size="small" data-testid="fp-move-down" :aria-label="`Move ${step.fabric_process} down`" title="Move process down" :disabled="!canMoveProcess(processes, index, 1)" @click="move(index, 1)" />
							<Button label="Edit" severity="secondary" outlined size="small" data-testid="fp-edit" :loading="busy === step.key" @click="openEdit(step, index)" />
							<Button icon="pi pi-times" text severity="secondary" size="small" data-testid="fp-remove" :aria-label="`Remove ${step.fabric_process}`" title="Remove step" @click="remove(step)" />
						</div>
					</div>
					<div class="ipd-fp-flow">
						<span class="ipd-fp-item">{{ inputItemLabel(step, item, conversionInputs) }}</span>
						<template v-if="hasConversion(step)"><span class="ipd-fp-arrow">→</span><span class="ipd-fp-item">{{ step.output_item }}</span></template>
						<span v-else class="ipd-fp-same">same item</span>
						<span v-if="ratioLabel(step)" class="ipd-fp-ratio">{{ ratioLabel(step) }}</span>
					</div>
					<div class="ipd-fp-summary">
						<span class="ipd-fp-summary__label">What changes</span>
						<!-- eslint-disable-next-line vue/no-v-html -- values are escaped by summaryOf -->
						<span class="ipd-fp-summary__text" v-html="summaryOf(step)" />
					</div>
					<template v-if="combinationRows(step).length">
						<button type="button" class="ipd-fp-toggle" data-testid="fp-toggle-detail" :aria-expanded="Boolean(expanded[step.key])" @click="expanded[step.key] = !expanded[step.key]">
							<i class="pi" :class="expanded[step.key] ? 'pi-chevron-down' : 'pi-chevron-right'" aria-hidden="true" />
							{{ expanded[step.key] ? "Hide combinations" : "View combinations" }}
							<span class="ipd-fp-muted">({{ combinationRows(step).length }})</span>
						</button>
						<!-- eslint-disable-next-line vue/no-v-html -- values are escaped by combinationRows -->
						<ul v-if="expanded[step.key]" class="ipd-fp-detail" data-testid="fp-detail-rows"><li v-for="(row, rowIndex) in combinationRows(step)" :key="rowIndex" v-html="row" /></ul>
					</template>
					<p v-for="message in cardErrors(step)" :key="message" class="ipd-cloth-strip ipd-cloth-strip--error" role="status">
						<i class="pi pi-exclamation-circle" aria-hidden="true" />{{ message }}
					</p>
				</li>
			</ol>

			<p v-if="notice" class="ipd-cloth-strip ipd-cloth-strip--error" role="status"><i class="pi pi-exclamation-circle" aria-hidden="true" />{{ notice }}</p>

			<div v-if="!readonly" class="ipd-fp-addbar">
				<div class="ipd-cloth-dialog__field ipd-fp-addbar__field">
					<label class="erp-field-label" for="ipd-fp-add-process">Add a process</label>
					<Select v-model="addProcessName" input-id="ipd-fp-add-process" :options="addOptions" placeholder="Pick a process…" filter fluid data-testid="fp-process-select" />
				</div>
				<Button :label="busy === 'add' ? 'Reading process…' : 'Add & define →'" data-testid="fp-add-btn" :disabled="!addProcessName || Boolean(busy)" @click="addProcess" />
			</div>
		</div>
		<FabricProcessDialog
			:draft="draft"
			:item="item"
			:conversion-inputs="conversionInputs"
			:attributes="attributes"
			:value-options="valueOptions"
			@save="saveDraft"
			@cancel="draft = null"
			@need-values="loadValues"
		/>
	</IpdSection>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import Button from "primevue/button"
import Select from "primevue/select"

import { callRead, getList } from "../../../../api/frappe.js"
import { searchItemAttributeValues } from "../../../../api/purchase.js"
import IpdSection from "../IpdSection.vue"
import FabricProcessDialog from "./FabricProcessDialog.vue"
import { canMoveProcess, moveProcess, nextSequence, removeProcess, rowKey } from "./clothGrids.js"
import { availableProcesses, buildSteps, combinationRows, hasConversion, inputItemLabel, ratioLabel, shapeOf, stepsToRows, summaryOf } from "./fabricProcessCards.js"
import { blankDraft, draftFromStep, draftToStep, transformShape } from "./fabricProcessDraft.js"
import { useClothSection } from "./useClothTable.js"
import "./cloth.css"

const props = defineProps({
	sectionKey: { type: String, required: true },
	readonly: { type: Boolean, default: false },
})

const { editor, readonly } = useClothSection(props)
const root = ref(null)
const processes = computed(() => editor.draft.fabric_processes || [])
const mappings = computed(() => editor.draft.fabric_value_mappings || [])
const steps = computed(() => buildSteps(processes.value, mappings.value))
const item = computed(() => editor.draft.item || "")
const conversionInputs = computed(() => (editor.draft.yarn_ratio_details || []).filter((row) => row.yarn_item).map((row) => ({ item: row.yarn_item, ratio: Number(row.ratio || 0) })))
const attributes = computed(() => [...new Set((editor.draft.item_attributes || []).map((row) => row.attribute).filter(Boolean))])
const context = computed(() => ({ item: item.value, conversionInputs: conversionInputs.value, defaultInput: conversionInputs.value[0]?.item || "" }))

const expanded = reactive({})
const valueOptions = reactive({})
const catalog = ref([])
const addProcessName = ref(null)
const addOptions = computed(() => availableProcesses(catalog.value, steps.value))
const draft = ref(null)
const busy = ref("")
const notice = ref("")

function writeBoth(next) {
	editor.setValues({ fabric_processes: next.processes, fabric_value_mappings: next.mappings })
}

const move = (index, direction) => writeBoth(moveProcess(processes.value, mappings.value, index, direction))
const remove = (step) => writeBoth(removeProcess(processes.value, mappings.value, step.key))

async function readShape(process) {
	return transformShape(await callRead("essdee_yrp.fabric_ipd.get_process_transform", { process }))
}

async function addProcess() {
	busy.value = "add"
	notice.value = ""
	try {
		const shape = await readShape(addProcessName.value)
		draft.value = reactive(blankDraft(addProcessName.value, nextSequence(processes.value), shape, context.value))
		addProcessName.value = null
	} catch (error) {
		notice.value = error?.message || "Could not read the process."
	} finally {
		busy.value = ""
	}
}

async function openEdit(step, index) {
	busy.value = step.key
	notice.value = ""
	try {
		const result = draftFromStep(step, index, await readShape(step.fabric_process), context.value)
		if (result.error) notice.value = `Cannot edit this step here: ${result.error} — editing it would rewrite or drop those entries.`
		else draft.value = reactive(result.draft)
	} catch (error) {
		notice.value = error?.message || "Could not read the process."
	} finally {
		busy.value = ""
	}
}

function saveDraft() {
	const current = draft.value
	const step = draftToStep(current, context.value)
	const next = [...steps.value]
	if (current.index == null) next.push(step)
	else next.splice(current.index, 1, { ...step, name: next[current.index].name })
	writeBoth(stepsToRows(next))
	draft.value = null
}

async function loadValues(names) {
	for (const attribute of names) {
		if (valueOptions[attribute]) continue
		valueOptions[attribute] = []
		const rows = await searchItemAttributeValues(attribute, "").catch(() => [])
		valueOptions[attribute] = (rows || []).map((row) => row.label)
	}
}

const processErrors = computed(() => editor.gridErrors("fabric_processes") || {})
const mappingErrors = computed(() => editor.gridErrors("fabric_value_mappings") || {})
function cardErrors(step) {
	const messages = Object.values(processErrors.value[step.key] || {})
	mappings.value.forEach((row, index) => {
		if (Number(row.sequence) !== step.sequence) return
		messages.push(...Object.values(mappingErrors.value[rowKey(row, index)] || {}))
	})
	return [...new Set(messages.filter(Boolean))]
}

async function loadCatalog() {
	if (readonly.value || catalog.value.length) return
	const rows = await getList("YRP Process", { fields: ["name"], filters: [["is_cloth_process", "=", 1]], orderBy: "name asc", pageLength: 0 })
	catalog.value = rows.map((row) => row.name)
}
watch(readonly, loadCatalog)

function focusCard(problem) {
	const key = problem.row_key || steps.value[0]?.key
	const card = root.value?.querySelector(`[data-fp-key="${CSS.escape(String(key))}"]`) || root.value
	card?.scrollIntoView({ block: "center" })
	return Boolean(card)
}
const unregister = []
onMounted(() => {
	loadCatalog()
	unregister.push(editor.registerFocus("fabric_processes", focusCard), editor.registerFocus("fabric_value_mappings", focusCard))
})
onBeforeUnmount(() => unregister.forEach((dispose) => dispose()))
</script>
