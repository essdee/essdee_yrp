<template>
	<DepartmentPage :title="config.label" :back-to="config.listPath" :back-label="config.pluralLabel" :show-title="false" flat full-width inline-navigation>
		<section class="action-master erp-workspace" :aria-busy="loading || Boolean(acting)">
			<header class="action-master__header">
				<div class="action-master__title">
					<InlinePageNavigation title-target="action-master-title" :show-document-navigation="Boolean(doc.name)" :current-name="doc.name || ''"
						:document-label="config.label" :navigation-disabled="(dirty && editable) || Boolean(acting)" />
					<h1 id="action-master-title" class="erp-doc-title">{{ heading }}</h1>
					<DocumentStatusBadge v-if="doc.name && isMaster" :docstatus="doc.docstatus" />
					<small v-if="doc.name">Quantity {{ doc.quantity || "—" }} · Lead Time {{ doc.lead_time || 0 }} days</small>
				</div>
				<div class="action-master__actions">
					<Button v-if="canCancel" label="Cancel" icon="pi pi-ban" severity="danger" outlined :disabled="Boolean(acting)" @click="confirmCancel" />
					<Button v-if="canAmend" label="Amend" icon="pi pi-copy" severity="secondary" outlined :disabled="Boolean(acting)" @click="confirmAmend" />
					<DocumentSaveButton v-if="editable" :saved="Boolean(doc.name)" :dirty="dirty" :docstatus="Number(doc.docstatus || 0)" :show-submit="isMaster && Boolean(permissions?.submit)"
						:document-label="`${config.label} ${doc.name || ''}`" :loading="acting === 'save' || acting === 'submit'" :disabled="Boolean(acting)" @save="save" @submit="submit" />
				</div>
			</header>
			<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<div v-else-if="loading" class="action-master__loading" role="status" :aria-label="`Loading ${config.label}`"><Skeleton v-for="index in 4" :key="index" height="3rem" /></div>
			<template v-else>
				<div class="action-master__fields">
					<template v-for="field in headerFields" :key="field.fieldname">
						<LinkField v-if="field.fieldname === 'action_master_template'" :model-value="header.action_master_template" :doctype="field.options" :label="field.label"
							:disabled="!editable" :allow-create="false" :show-open-button="false" @update:model-value="setHeader(field.fieldname, $event)" />
						<FormField v-else :field="field" :model-value="header[field.fieldname]" :form="header"
							:disabled="!editable" :show-open-button="false" @update:model-value="setHeader(field.fieldname, $event)" />
					</template>
				</div>
				<ActionMasterSteps v-model:steps="steps" :disabled="!editable" @update:steps="dirty = true" />
			</template>
		</section>
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Skeleton from "primevue/skeleton"
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { callMethod, cancelDoc, createDoc, getDoc, getMeta, submitDoc, updateDoc } from "../../../api/frappe.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import FormField from "../../../components/common/FormField.vue"
import LinkField from "../../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import InlinePageNavigation from "../../../components/navigation/InlinePageNavigation.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import DocumentSaveButton from "../../../components/documents/DocumentSaveButton.vue"
import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"
import { useDocumentPermissions } from "../../../composables/useDocumentPermissions.js"
import { canCreateDoctype } from "../../../utils/linkTarget.js"
import { useActionConfirmation } from "../../../utils/useActionConfirmation.js"
import ActionMasterSteps from "./ActionMasterSteps.vue"
import { ACTION_MASTER_KINDS, TEMPLATE_METHOD, actionMasterPayload, headerValues, newStep, stepsFromDoc } from "./actionMaster.js"

/** New, draft, submitted and cancelled Action Masters (or Templates) on one full-width page, like the Desk form. */
const props = defineProps({
	kind: { type: String, default: "master" },
	documentName: { type: String, default: "" },
})
const config = computed(() => ACTION_MASTER_KINDS[props.kind])
const doctype = computed(() => config.value.doctype)
const isMaster = computed(() => props.kind === "master")
const route = useRoute()
const router = useRouter()
const confirmAction = useActionConfirmation()
const doc = ref({})
const header = ref({})
const steps = ref([])
const fields = ref([])
const loading = ref(true)
const loadError = ref("")
const error = ref("")
const acting = ref("")
const dirty = ref(false)
const amendFrom = computed(() => props.documentName || !isMaster.value ? "" : String(route.query.amend_from || ""))
const permissions = useDocumentPermissions(() => [doctype.value, doc.value.name, doc.value.docstatus])
const heading = computed(() => doc.value.name || (amendFrom.value ? `Amend ${amendFrom.value}` : `New ${config.value.label}`))
const editable = computed(() => doc.value.name ? doc.value.docstatus === 0 && Boolean(permissions.value?.write) : canCreateDoctype(doctype.value))
const canCancel = computed(() => doc.value.docstatus === 1 && Boolean(permissions.value?.cancel))
const canAmend = computed(() => doc.value.docstatus === 2 && Boolean(permissions.value?.amend))
const headerFields = computed(() => config.value.headerFields.map((fieldname) => fields.value.find((field) => field.fieldname === fieldname)).filter(Boolean))
let sequence = 0

async function load() {
	const requested = ++sequence
	loading.value = true
	loadError.value = ""
	try {
		const source = props.documentName || amendFrom.value
		const [metas, loaded] = await Promise.all([getMeta(doctype.value), source ? getDoc(doctype.value, source) : null])
		if (requested !== sequence) return
		fields.value = metas.find((meta) => meta.name === doctype.value)?.fields || []
		show(props.documentName ? loaded : {}, loaded || {})
	} catch (reason) {
		if (requested === sequence) loadError.value = reason?.message || `Unable to load the ${config.value.label}.`
	} finally {
		if (requested === sequence) loading.value = false
	}
}

function show(record, values = record) {
	doc.value = record || {}
	header.value = headerValues(config.value.headerFields, values)
	steps.value = stepsFromDoc(values)
	if (!record?.name && !steps.value.length) steps.value = [newStep()]
	dirty.value = !record?.name
}

async function setHeader(fieldname, value) {
	header.value = { ...header.value, [fieldname]: value }
	dirty.value = true
	if (fieldname !== "action_master_template" || !value) return
	try {
		steps.value = (await callMethod(TEMPLATE_METHOD, { template: value })).map((row) => newStep(row))
	} catch (reason) {
		error.value = reason?.message || "Unable to load the Action Master Template."
	}
}

async function run(action, change) {
	acting.value = action
	try {
		const saved = await change()
		if (saved?.name !== props.documentName) return router.replace({ name: config.value.routes.view, params: { documentName: saved.name } })
		show(await getDoc(doctype.value, saved.name))
	} catch (reason) {
		error.value = reason?.message || `Unable to ${action} the ${config.value.label}.`
	} finally {
		acting.value = ""
	}
}

function save() {
	const payload = actionMasterPayload(header.value, steps.value, amendFrom.value)
	return run("save", () => doc.value.name ? updateDoc(doctype.value, doc.value.name, { ...payload, modified: doc.value.modified }) : createDoc(doctype.value, payload))
}

function submit() {
	return run("submit", async () => (await submitDoc(doctype.value, doc.value.name, doc.value.modified), doc.value))
}

function confirmCancel() {
	const { name, modified } = doc.value
	confirmAction({
		header: "Cancel Action Master?",
		message: `Cancel Action Master ${name}? New Time and Actions can no longer use it.`,
		acceptLabel: "Cancel Action Master",
		acceptIcon: "pi pi-ban",
		accept: () => run("cancel", async () => (await cancelDoc(doctype.value, name, modified), doc.value)),
	})
}

function confirmAmend() {
	const { name } = doc.value
	confirmAction({
		header: "Amend Action Master?",
		message: `Create an amended draft from Action Master ${name}?`,
		acceptLabel: "Amend Action Master",
		acceptIcon: "pi pi-copy",
		acceptSeverity: "primary",
		accept: () => router.push({ name: config.value.routes.new, query: { amend_from: name } }),
	})
}

watch(() => [props.kind, props.documentName, amendFrom.value], load, { immediate: true })
</script>

<style scoped>
.action-master { display: grid; gap: var(--erp-space-4, 16px); }
.action-master__header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--erp-space-3, 12px); }
.action-master__title { display: flex; flex-wrap: wrap; align-items: center; gap: var(--erp-space-2, 8px); }
.action-master__title h1 { margin: 0; }
.action-master__title small { color: var(--erp-text-muted); }
.action-master__actions { display: flex; flex-wrap: wrap; gap: var(--erp-space-2, 8px); }
.action-master__fields { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: var(--erp-space-3, 12px); }
.action-master__loading { display: grid; gap: var(--erp-space-2, 8px); }
@media (max-width: 640px) {
	.action-master { gap: var(--erp-space-3, 12px); }
	.action-master__fields { grid-template-columns: minmax(0, 1fr); }
	.action-master__actions { width: 100%; }
	.action-master__actions > * { flex: 1 1 auto; }
}
@media (max-width: 640px) {
	.action-master { gap: var(--erp-space-3, 12px); }
	.action-master__fields { grid-template-columns: minmax(0, 1fr); }
	.action-master__actions { width: 100%; }
}
</style>
