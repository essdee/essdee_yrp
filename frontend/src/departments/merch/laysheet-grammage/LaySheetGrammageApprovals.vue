<template>
	<DepartmentPage title="LaySheet Grammage Approval" back-to="/merch" back-label="Merch" :show-title="false" flat full-width inline-navigation>
		<section class="grammage-approval erp-workspace" aria-labelledby="grammage-approval-title">
			<header class="grammage-approval__header">
				<h1 id="grammage-approval-title">LaySheet Grammage Approval</h1>
				<Button label="Refresh" icon="pi pi-refresh" severity="secondary" outlined size="small" :loading="loading" :disabled="approving" @click="load" />
			</header>
			<div class="grammage-approval__filters">
				<LinkField v-for="filter in GRAMMAGE_FILTERS" :key="filter.key" v-model="filters[filter.key]" :doctype="filter.doctype" :label="filter.label" :show-open-button="false" show-clear :disabled="approving" />
			</div>
			<Message v-if="notice" severity="success" closable @close="notice = ''">{{ notice }}</Message>
			<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<template v-else>
				<div v-if="canApprove && selectedRows.length" class="grammage-approval__bulk-bar">
					<strong>{{ selectedRows.length }} selected</strong>
					<div class="grammage-approval__bulk-actions">
						<Button :label="`Approve (${selectedRows.length})`" icon="pi pi-check" size="small" :loading="approving" @click="approve(selectedRows)" />
						<Button icon="pi pi-times" severity="secondary" text rounded size="small" aria-label="Clear selection" :disabled="approving" @click="selectedRows = []" />
					</div>
				</div>
				<DataTable v-model:selection="selectedRows" :value="rows" :loading="loading" data-key="name" class="premium-list-table" row-hover scrollable
					:table-style="{ minWidth: '960px' }" :pt="{ tableContainer: { tabindex: 0, role: 'region', 'aria-label': 'LaySheets pending grammage approval' } }" @row-click="openRow">
					<Column v-if="canApprove" selection-mode="multiple" header-style="width: 44px" body-style="width: 44px; text-align: center" />
					<Column v-for="column in GRAMMAGE_COLUMNS" :key="column.field" :field="column.field" :header="column.label"
						:header-class="column.numeric ? 'list-number-column' : ''" :body-class="column.numeric ? 'list-number-column' : ''">
						<template #body="{ data }">{{ grammageCellText(data, column) }}</template>
					</Column>
					<template #empty><p class="grammage-approval__empty">{{ loading ? "Loading…" : "No Cutting LaySheets are pending grammage approval." }}</p></template>
				</DataTable>
			</template>
		</section>
		<Dialog v-model:visible="detailVisible" modal :header="detail ? `LaySheet ${detail.name}` : 'LaySheet'" class="erp-dialog--sm">
			<dl v-if="detail" class="grammage-approval__detail">
				<template v-for="column in GRAMMAGE_COLUMNS" :key="column.field">
					<dt>{{ column.label }}</dt>
					<dd>{{ grammageCellText(detail, column) }}</dd>
				</template>
			</dl>
			<template #footer>
				<Button label="Close" text severity="secondary" :disabled="approving" @click="detailVisible = false" />
				<Button v-if="canApprove" label="Approve" icon="pi pi-check" :loading="approving" @click="approve([detail])" />
			</template>
		</Dialog>
		<ListBulkResultDialog v-model:visible="resultVisible" :outcome="outcome" />
		<DocumentErrorDialog :message="actionError" @dismiss="actionError = ''" />
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Column from "primevue/column"
import DataTable from "primevue/datatable"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import { onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"

import { approveGrammageLaySheets, getPendingGrammageLaySheets } from "../../../api/merch.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import LinkField from "../../../components/common/LinkField.vue"
import ListBulkResultDialog from "../../../components/common/ListBulkResultDialog.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import { applyApprovalResult, emptyGrammageFilters, GRAMMAGE_COLUMNS, GRAMMAGE_FILTERS, grammageCellText, grammageFilterArgs } from "./laysheetGrammageApproval.js"

/** Cutting LaySheets in Approval Pending; the server decides who may approve. */
const filters = reactive(emptyGrammageFilters())
const rows = ref([])
const selectedRows = ref([])
const canApprove = ref(false)
const loading = ref(false)
const loadError = ref("")
const approving = ref(false)
const notice = ref("")
const actionError = ref("")
const outcome = ref(null)
const resultVisible = ref(false)
const detail = ref(null)
const detailVisible = ref(false)
let request = 0

async function load() {
	const current = ++request
	loading.value = true
	loadError.value = ""
	try {
		const result = await getPendingGrammageLaySheets(grammageFilterArgs(filters))
		if (current !== request) return
		rows.value = result?.rows || []
		canApprove.value = Boolean(result?.can_approve)
		selectedRows.value = []
	} catch (error) {
		if (current === request) loadError.value = error.message || "Unable to load Cutting LaySheets."
	} finally {
		if (current === request) loading.value = false
	}
}

function openRow(event) {
	if (event.originalEvent?.target?.closest?.(".p-checkbox, .p-selection-column, button, a, input")) return
	detail.value = event.data
	detailVisible.value = true
}

async function approve(selection) {
	if (!canApprove.value || !selection.length || approving.value) return
	approving.value = true
	notice.value = ""
	try {
		const result = applyApprovalResult(rows.value, await approveGrammageLaySheets(selection.map((row) => row.name)))
		rows.value = result.rows
		selectedRows.value = selectedRows.value.filter((row) => result.rows.includes(row))
		notice.value = result.notice
		outcome.value = result.outcome
		resultVisible.value = Boolean(result.outcome)
		detailVisible.value = false
	} catch (error) {
		actionError.value = error.message || "Unable to approve grammage."
	} finally {
		approving.value = false
	}
}

watch(filters, load)
onMounted(load)
onBeforeUnmount(() => { ++request })
</script>

<style scoped>
.grammage-approval { display: grid; width: 100%; min-width: 0; gap: var(--erp-space-3); padding: var(--erp-space-2) 0 var(--erp-space-5); }
.grammage-approval__header { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-3); }
.grammage-approval__header h1 { margin: 0; font-size: 1.25rem; }
.grammage-approval__filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: var(--erp-space-3); }
.grammage-approval__bulk-bar { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-3); padding: var(--erp-space-2) var(--erp-space-3); border: 1px solid var(--erp-border); border-radius: var(--erp-radius-md); }
.grammage-approval__bulk-actions { display: flex; align-items: center; gap: var(--erp-space-2); }
.grammage-approval__empty { margin: 0; padding: var(--erp-space-4); text-align: center; }
.grammage-approval__detail { display: grid; grid-template-columns: auto 1fr; gap: var(--erp-space-2) var(--erp-space-4); margin: 0; }
.grammage-approval__detail dt { color: var(--erp-text-muted); }
.grammage-approval__detail dd { margin: 0; overflow-wrap: anywhere; }
:deep(.list-number-column) { text-align: right; }
</style>
