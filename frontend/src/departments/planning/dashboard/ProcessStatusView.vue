<template>
	<div class="pd-view">
		<section class="pd-panel pd-head" aria-labelledby="pd-process-status-title">
			<div class="pd-head__row">
				<div class="pd-head__title">
					<InlinePageNavigation :show-back="false" />
					<div>
						<h1 id="pd-process-status-title">Process Status</h1>
						<p>Every IPD process of each open lot, fabric first. Hover a cell for its Work Orders; click it for the size-wise detail.</p>
					</div>
				</div>
				<div class="pd-head__end">
					<span v-if="dashboard" class="pd-sync"><i aria-hidden="true" />Live · {{ formatDisplayDate(dashboard.as_of) }}</span>
					<Button icon="pi pi-refresh" label="Refresh" size="small" severity="secondary" outlined :loading="loading" @click="load" />
				</div>
			</div>
			<div class="pd-filters pd-filters--five" role="search" aria-label="Process Status filters">
				<FilterMultiSelect v-for="filter in FILTERS" :key="filter.kind" :model-value="activeFilters[filter.kind]" :label="filter.label" :placeholder="filter.placeholder" :options="options[filter.kind]" @update:model-value="setFilter(filter.kind, $event)" />
				<Button label="Clear" text size="small" class="pd-filters__clear" :disabled="!hasDashboardFilter(activeFilters)" @click="clear" />
			</div>
			<p class="pd-ps-legend pd-muted">
				<span><b>-</b> not in the lot's IPDs</span>
				<span v-for="(tone, label) in CELL_TONES" :key="label"><span class="pd-status" :class="`pd-status--${tone}`">{{ label }}</span></span>
				<span>Completed = every Work Order fully received, billed or closed; In Progress shows received %.</span>
			</p>
		</section>
		<div v-if="loading && !dashboard" class="pd-loading"><Skeleton height="96px" /><Skeleton height="420px" /></div>
		<WorkspaceLoadError v-else-if="error" :message="error" :loading="loading" @retry="load" />
		<section v-else-if="dashboard" class="pd-panel pd-section" aria-label="Process status table">
			<header class="pd-toolbar">
				<div>
					<h2>Lots</h2>
					<p :data-count="rows.length">{{ rangeText }} · {{ formatQuantity(processes.length) }} {{ processes.length === 1 ? "process" : "processes" }}</p>
				</div>
			</header>
			<div class="pd-table-wrap pd-table-wrap--scroll">
				<table class="pd-table pd-ps-table">
					<thead>
						<tr>
							<th class="pd-number">#</th><th>PPO</th><th>Lot</th><th>Item</th><th>PPO Status</th><th>Lot Status</th>
							<th class="pd-number">PPO Qty</th><th class="pd-number">Lot Qty</th>
							<th v-for="process in processes" :key="process.name" :class="`pd-ps-col--${process.kind}`" :data-process="process.name">{{ process.name }}</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="(row, index) in shown.rows" :key="row.lot" :data-row="row.lot">
							<td class="pd-number pd-muted">{{ index + 1 }}</td>
							<td>{{ row.ppo }}</td>
							<td><b>{{ row.lot }}</b></td>
							<td class="pd-ps-item" :title="row.item">{{ row.item }}</td>
							<td><LotStatusPill :status="row.ppoStatus" /></td>
							<td><LotStatusPill :status="row.status" /></td>
							<td class="pd-number">{{ formatQuantity(row.ppo_qty) }}</td>
							<td class="pd-number">{{ formatQuantity(row.qty) }}<small v-if="row.is_set" class="pd-sub">sets</small></td>
							<td v-for="process in processes" :key="process.name" :data-cell="process.name" @mouseenter="card?.show($event.currentTarget, row, process.name)" @mouseleave="card?.scheduleHide()" @focusin="card?.show($event.currentTarget, row, process.name)" @focusout="card?.scheduleHide()">
								<span v-if="views[index][process.name].tone === 'none'" class="pd-muted">{{ NOT_IN_IPD }}</span>
								<button v-else-if="views[index][process.name].isClickable" type="button" class="pd-ps-cell" @click="openCell($event, row, process.name)">
									<CellPill :view="views[index][process.name]" />
								</button>
								<CellPill v-else :view="views[index][process.name]" />
							</td>
						</tr>
						<tr v-if="shown.hasMore" ref="sentinel" class="pd-more-row"><td :colspan="processes.length + 8">Loading more lots…</td></tr>
						<tr v-if="!shown.rows.length"><td :colspan="processes.length + 8" class="pd-empty">No lots match these filters.</td></tr>
					</tbody>
				</table>
			</div>
		</section>
		<ProcessCellCard ref="card" :reports="reports" />
		<Menu ref="menu" :model="menuItems" popup />
		<ProcessDetailDialog v-model:visible="dialogVisible" :row="dialogRow" :step="dialogStep" :mode="dialogStep?.kind === 'cloth' ? 'colour' : 'size'" :reports="reports" />
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Menu from "primevue/menu"
import Skeleton from "primevue/skeleton"
import { computed, h, onMounted, reactive, ref } from "vue"

import { getPlanningDashboard, getPlanningProcessStatus } from "../../../api/planning.js"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import InlinePageNavigation from "../../../components/navigation/InlinePageNavigation.vue"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import FilterMultiSelect from "./FilterMultiSelect.vue"
import LotStatusPill from "./LotStatusPill.vue"
import ProcessCellCard from "./ProcessCellCard.vue"
import ProcessDetailDialog from "./ProcessDetailDialog.vue"
import { formatQuantity, plural } from "./dashboardFormat.js"
import { dashboardOptions, emptyDashboardFilters, filterDashboardRows, hasDashboardFilter } from "./dashboardRows.js"
import { useRowWindow } from "./rowWindow.js"
import { CELL_TONES, NOT_IN_IPD, cellView, processStatusRows, visibleProcesses } from "./processStatusRows.js"

/** Dashboard lots with one column per IPD process; a cell opens the PPO Tracking process detail. */
const props = defineProps({
	reports: { type: Array, default: () => [] },
	category: { type: Array, default: () => [] },
})
const emit = defineEmits(["update:category"])
const FILTERS = [
	{ kind: "ppo", label: "PPO", placeholder: "All PPOs" },
	{ kind: "lot", label: "Lot", placeholder: "All lots" },
	{ kind: "item", label: "Item", placeholder: "All items" },
	{ kind: "product_category", label: "Product Category", placeholder: "All categories" },
	{ kind: "status", label: "Lot Status", placeholder: "All statuses" },
]
const CellPill = ({ view }) => h("span", { class: ["pd-status", `pd-status--${view.tone}`] }, view.percent === null ? view.label : `${view.label} · ${view.percent}%`)
const dashboard = ref(null)
const status = ref({ processes: [], lots: {} })
const loading = ref(false)
const error = ref("")
const filters = reactive(emptyDashboardFilters())
const activeFilters = computed(() => ({ ...filters, product_category: props.category }))
const menu = ref(null)
const card = ref(null)
const menuItems = ref([])
const dialogVisible = ref(false)
const dialogRow = ref({})
const dialogStep = ref(null)

const allRows = computed(() => (dashboard.value ? processStatusRows(dashboard.value, status.value) : []))
const rows = computed(() => filterDashboardRows(allRows.value, activeFilters.value))
const processes = computed(() => visibleProcesses(status.value.processes, rows.value))
const { shown, sentinel } = useRowWindow(rows)
const views = computed(() => shown.value.rows.map((row) => Object.fromEntries(processes.value.map(({ name }) => [name, cellView(row, name)]))))
const options = computed(() => Object.fromEntries(FILTERS.map(({ kind }) => [kind, dashboardOptions(dashboard.value?.lots || [], activeFilters.value, kind, dashboard.value?.ppos)])))
const rangeText = computed(() => (rows.value.length ? plural(rows.value.length, "lot") : "No lots"))

async function load() {
	loading.value = true
	error.value = ""
	try {
		const [dashboardData, statusData] = await Promise.all([getPlanningDashboard(), getPlanningProcessStatus()])
		dashboard.value = dashboardData
		status.value = statusData
	} catch (reason) {
		error.value = reason?.message || "Unable to load the Process Status."
	} finally {
		loading.value = false
	}
}

function setFilter(kind, values) {
	if (kind === "product_category") emit("update:category", values)
	else filters[kind] = values
}

function clear() {
	Object.assign(filters, emptyDashboardFilters())
	if (props.category.length) emit("update:category", [])
}

function openStep(row, step) {
	dialogRow.value = row
	dialogStep.value = step
	dialogVisible.value = true
}

function openCell(event, row, process) {
	card.value?.hide()
	const steps = row.cells[process].steps
	if (steps.length === 1) return openStep(row, steps[0])
	menuItems.value = steps.map((step) => ({ label: step.name, command: () => openStep(row, step) }))
	menu.value?.toggle(event)
}

onMounted(load)
</script>

<style scoped>
.pd-head__title { display: flex; min-width: 0; align-items: center; gap: 10px; }
.pd-head__title > div { min-width: 0; }
.pd-ps-legend { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; margin: 10px 0 0; font-size: 12px; }
.pd-ps-table th, .pd-ps-table td { padding: 7px 8px; }
.pd-ps-table th { font-size: 10.5px; letter-spacing: .04em; text-transform: uppercase; }
.pd-ps-table .pd-status { gap: 4px; padding: .15rem .45rem; font-size: 11px; }
.pd-ps-table tbody tr:nth-child(even) td { background: var(--erp-surface-soft); }
.pd-ps-table td:nth-child(3) { position: sticky; left: 0; z-index: 1; background: var(--erp-surface); box-shadow: 1px 0 0 var(--erp-border); }
.pd-ps-table th:nth-child(3) { position: sticky; top: 0; left: 0; z-index: 3; box-shadow: 1px 0 0 var(--erp-border); }
.pd-ps-table .pd-ps-item { max-width: 220px; overflow: hidden; text-overflow: ellipsis; }
.pd-ps-table th.pd-ps-col--fabric { background: var(--pd-blue-fill); }
.pd-ps-cell { padding: 0; border: 0; background: none; cursor: pointer; }
.pd-ps-cell:hover .pd-status, .pd-ps-cell:focus-visible .pd-status { text-decoration: underline; }
</style>
