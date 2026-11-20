<template>
	<DepartmentPage title="LaySheet Grammage Approval" back-to="/merch" back-label="Merch" :show-title="false" flat full-width inline-navigation>
		<section class="grammage-approval erp-workspace" aria-labelledby="grammage-approval-title">
			<header class="grammage-approval__header">
				<h1 id="grammage-approval-title">LaySheet Grammage Approval</h1>
				<div class="grammage-approval__header-actions">
					<Button class="grammage-approval__filter-toggle" :label="activeFilterCount ? `Filters (${activeFilterCount})` : 'Filters'" icon="pi pi-filter" severity="secondary" outlined size="small"
						:aria-expanded="filtersOpen" aria-controls="grammage-approval-filters" @click="filtersOpen = !filtersOpen" />
					<Button label="Refresh" icon="pi pi-refresh" severity="secondary" outlined size="small" :loading="loading" :disabled="approving" @click="load" />
				</div>
			</header>
			<div id="grammage-approval-filters" class="grammage-approval__filters" :class="{ 'is-open': filtersOpen }">
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
				<div class="grammage-approval__cards" aria-label="LaySheets pending grammage approval">
					<label v-if="canApprove && rows.length" class="grammage-approval__select-all">
						<Checkbox :model-value="allSelected" binary :disabled="approving" @update:model-value="selectedRows = $event ? [...rows] : []" />
						<span>Select all ({{ rows.length }})</span>
					</label>
					<article v-for="row in rows" :key="row.name" class="grammage-card" :class="{ 'is-selected': selectedRows.includes(row) }" @click="openRow({ originalEvent: $event, data: row })">
						<div class="grammage-card__head">
							<Checkbox v-if="canApprove" v-model="selectedRows" :value="row" :disabled="approving" :aria-label="`Select LaySheet ${row.name}`" />
							<strong class="grammage-card__lot">{{ grammageCellText(row, CARD_COLUMNS.lot) }}</strong>
							<Button v-if="canApprove" class="grammage-card__approve" label="Approve" icon="pi pi-check" size="small" outlined :disabled="approving" @click="approve([row])" />
						</div>
						<p class="grammage-card__refs">{{ grammageCellText(row, CARD_COLUMNS.posting_date) }} · {{ grammageCellText(row, CARD_COLUMNS.cutting_plan) }} · {{ grammageCellText(row, CARD_COLUMNS.work_order) }} · Lay {{ grammageCellText(row, CARD_COLUMNS.lay_no) }}</p>
						<p class="grammage-card__item">{{ grammageCellText(row, CARD_COLUMNS.item_name) }}</p>
						<dl class="grammage-card__weights">
							<div><dt>REQD</dt><dd>{{ grammageCellText(row, CARD_COLUMNS.required_pcs_weight) }}</dd></div>
							<div><dt>Actual</dt><dd>{{ grammageCellText(row, CARD_COLUMNS.piece_weight) }}</dd></div>
							<div><dt>Diff</dt><dd :class="`is-${grammageDifference(row).tone}`">{{ grammageDifference(row).text }}</dd></div>
						</dl>
					</article>
					<p v-if="!rows.length" class="grammage-approval__empty">{{ loading ? "Loading…" : "No Cutting LaySheets are pending grammage approval." }}</p>
				</div>
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
import Checkbox from "primevue/checkbox"
import Column from "primevue/column"
import DataTable from "primevue/datatable"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"

import { approveGrammageLaySheets, getPendingGrammageLaySheets } from "../../../api/merch.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import LinkField from "../../../components/common/LinkField.vue"
import ListBulkResultDialog from "../../../components/common/ListBulkResultDialog.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import { applyApprovalResult, emptyGrammageFilters, GRAMMAGE_COLUMNS, GRAMMAGE_FILTERS, grammageCellText, grammageDifference, grammageFilterArgs } from "./laysheetGrammageApproval.js"

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
const filtersOpen = ref(false)
const activeFilterCount = computed(() => Object.values(filters).filter(Boolean).length)
const allSelected = computed(() => rows.value.length > 0 && selectedRows.value.length === rows.value.length)
const CARD_COLUMNS = Object.fromEntries(GRAMMAGE_COLUMNS.map((column) => [column.field, column]))
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
.grammage-approval { display: grid; grid-template-columns: minmax(0, 1fr); width: 100%; min-width: 0; gap: var(--erp-space-3); padding: var(--erp-space-2) 0 var(--erp-space-5); }
.grammage-approval__header { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-3); }
.grammage-approval__header h1 { margin: 0; font-size: 1.25rem; }
.grammage-approval__header-actions { display: flex; align-items: center; gap: var(--erp-space-2); }
.grammage-approval__filter-toggle, .grammage-approval__cards { display: none; }
.grammage-approval__filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: var(--erp-space-3); }
.grammage-approval__bulk-bar { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-3); padding: var(--erp-space-2) var(--erp-space-3); border: 1px solid var(--erp-border); border-radius: var(--erp-radius-md); }
.grammage-approval__bulk-actions { display: flex; align-items: center; gap: var(--erp-space-2); }
.grammage-approval__empty { margin: 0; padding: var(--erp-space-4); text-align: center; }
.grammage-approval__detail { display: grid; grid-template-columns: auto 1fr; gap: var(--erp-space-2) var(--erp-space-4); margin: 0; }
.grammage-approval__detail dt { color: var(--erp-text-muted); }
.grammage-approval__detail dd { margin: 0; overflow-wrap: anywhere; }
:deep(.list-number-column) { text-align: right; }
@media (max-width: 640px) {
	.grammage-approval { gap: var(--erp-space-2); }
	.grammage-approval__header { flex-wrap: wrap; }
	.grammage-approval__header h1 { font-size: 1.125rem; }
	.grammage-approval__filter-toggle { display: inline-flex; }
	.grammage-approval__filters { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--erp-space-2); }
	.grammage-approval__filters:not(.is-open) { display: none; }
	.grammage-approval__bulk-bar { position: sticky; top: var(--erp-shell-header-height, 52px); z-index: 2; background: var(--erp-surface); box-shadow: 0 2px 6px rgb(0 0 0 / 8%); }
	.grammage-approval :deep(.premium-list-table) { display: none; }
	.grammage-approval__cards { display: grid; gap: var(--erp-space-2); }
	.grammage-approval__select-all { display: flex; align-items: center; gap: var(--erp-space-2); min-height: 40px; font-size: 0.875rem; color: var(--erp-text-secondary); }
	.grammage-card { display: grid; gap: 4px; padding: var(--erp-space-3); border: 1px solid var(--erp-border); border-radius: var(--erp-radius-md); background: var(--erp-surface); cursor: pointer; }
	.grammage-card.is-selected { border-color: var(--erp-accent-border); background: var(--erp-accent-soft); }
	.grammage-card__head { display: flex; align-items: center; gap: var(--erp-space-2); min-width: 0; }
	.grammage-card__lot { flex: 1; min-width: 0; overflow-wrap: anywhere; font-size: 0.9375rem; }
	.grammage-card__refs, .grammage-card__item { margin: 0; font-size: 0.8125rem; color: var(--erp-text-secondary); overflow-wrap: anywhere; }
	.grammage-card__item { color: var(--erp-text); font-size: 0.875rem; }
	.grammage-card__weights { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--erp-space-2); margin: 4px 0 0; padding: var(--erp-space-2); border-radius: var(--erp-radius-sm); background: var(--erp-surface-muted); }
	.grammage-card__weights dt { font-size: 0.6875rem; font-weight: 600; text-transform: uppercase; color: var(--erp-text-muted); }
	.grammage-card__weights dd { margin: 0; font-size: 0.9375rem; font-weight: 600; font-variant-numeric: tabular-nums; }
	.grammage-card__weights dd.is-over { color: var(--erp-danger); }
	.grammage-card__weights dd.is-under { color: var(--erp-success-text); }
	.grammage-card__approve { flex: none; min-height: 40px; }
	.grammage-approval__detail { grid-template-columns: minmax(0, 1fr); gap: 2px; }
	.grammage-approval__detail dd { margin-bottom: var(--erp-space-2); }
}
</style>
