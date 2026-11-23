<template>
	<Dialog v-model:visible="visible" modal dismissable-mask header="Links" class="linked-documents-dialog erp-dialog--md">
		<p v-if="loading" class="linked-documents-dialog__note">Loading…</p>
		<p v-else-if="error" class="linked-documents-dialog__error" role="alert">{{ error }}</p>
		<div v-else-if="!groups.length" class="erp-empty-state"><i class="pi pi-link"></i><strong>No linked documents</strong></div>
		<div v-else class="linked-documents-dialog__groups">
			<p class="linked-documents-dialog__note">Documents linked with <strong>{{ docname }}</strong></p>
			<section v-for="group in groups" :key="group.doctype" class="linked-documents-dialog__group">
				<header>{{ group.doctype }} <span>{{ group.rows.length }}</span></header>
				<ul>
					<li v-for="row in group.rows" :key="row.name">
						<a :href="row.href" @click="open($event, row)">{{ row.name }}</a>
						<DocumentStatusBadge :docstatus="row.docstatus" :label="row.status" />
					</li>
					<li v-if="group.hiddenCount" class="linked-documents-dialog__hidden">{{ group.hiddenCount }} restricted {{ group.hiddenCount === 1 ? "document" : "documents" }}</li>
				</ul>
			</section>
		</div>
	</Dialog>
</template>

<script setup>
import Dialog from "primevue/dialog"
import { ref, watch } from "vue"
import { useRouter } from "vue-router"

import { getLinkedDocuments } from "../../api/frappe.js"
import { linkedDocumentGroups } from "../../utils/linkedDocuments.js"
import DocumentStatusBadge from "./DocumentStatusBadge.vue"

/** Desk-style "Links" dialog: every document that links to this one, grouped by doctype. */
const props = defineProps({
	doctype: { type: String, required: true },
	docname: { type: String, required: true },
})
const visible = defineModel("visible", { type: Boolean, default: false })
const router = useRouter()
const groups = ref([])
const loading = ref(false)
const error = ref("")

watch(visible, (open) => { if (open) load() }, { immediate: true })

async function load() {
	loading.value = true
	error.value = ""
	try {
		groups.value = linkedDocumentGroups(await getLinkedDocuments(props.doctype, props.docname))
	} catch (reason) {
		error.value = reason?.message || "Linked documents could not be loaded."
	} finally {
		loading.value = false
	}
}

function open(event, row) {
	if (!row.route || event.button || event.ctrlKey || event.metaKey || event.shiftKey) return
	event.preventDefault()
	visible.value = false
	router.push(row.route)
}
</script>

<style scoped>
.linked-documents-dialog__groups { display: grid; gap: 14px; }
.linked-documents-dialog__note { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-table); }
.linked-documents-dialog__error { margin: 0; color: var(--erp-danger); }
.linked-documents-dialog__group { border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); overflow: hidden; }
.linked-documents-dialog__group header { display: flex; justify-content: space-between; padding: 7px 12px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-min); font-weight: var(--erp-font-weight-semibold); background: var(--erp-bg); border-bottom: 1px solid var(--erp-border); }
.linked-documents-dialog__group ul { margin: 0; padding: 0; list-style: none; }
.linked-documents-dialog__group li { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 7px 12px; font-size: var(--erp-font-size-table); }
.linked-documents-dialog__group li + li { border-top: 1px solid var(--erp-border); }
.linked-documents-dialog__group a { color: var(--erp-accent); font-weight: var(--erp-font-weight-semibold); text-decoration: none; overflow-wrap: anywhere; }
.linked-documents-dialog__group a:hover { text-decoration: underline; }
.linked-documents-dialog__hidden { color: var(--erp-text-muted); }
</style>
