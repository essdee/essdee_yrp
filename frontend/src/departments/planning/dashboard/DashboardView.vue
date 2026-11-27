<template>
	<div class="pd-view">
		<section class="pd-panel pd-head" aria-labelledby="pd-dashboard-title">
			<div class="pd-head__row">
				<div class="pd-head__title">
					<InlinePageNavigation :show-back="false" />
					<div>
						<h1 id="pd-dashboard-title">Dashboard</h1>
						<p>{{ formatQuantity(ppoTotal) }} open PPOs; their open lots below. Filters narrow every section and the cards add up the table's lots; click a figure, PPO or Lot to open it in PPO Tracking.</p>
					</div>
				</div>
				<div class="pd-head__end">
					<span v-if="data" class="pd-sync"><i aria-hidden="true" />Live · {{ formatDisplayDate(data.as_of) }}</span>
					<Button icon="pi pi-refresh" label="Refresh" size="small" severity="secondary" outlined :loading="loading" @click="load" />
				</div>
			</div>
			<div class="pd-filters pd-filters--five" role="search" aria-label="Dashboard filters">
				<FilterMultiSelect v-for="filter in FILTERS" :key="filter.kind" :model-value="activeFilters[filter.kind]" :label="filter.label" :placeholder="filter.placeholder" :options="options[filter.kind]" @update:model-value="setFilter(filter.kind, $event)" />
				<Button label="Clear" text size="small" class="pd-filters__clear" :disabled="!hasDashboardFilter(activeFilters)" @click="clear" />
			</div>
		</section>
		<div v-if="loading && !data" class="pd-loading"><Skeleton height="96px" /><Skeleton height="160px" /><Skeleton height="420px" /></div>
		<WorkspaceLoadError v-else-if="error" :message="error" :loading="loading" @retry="load" />
		<template v-else-if="data">
			<SummaryTiles :tiles="tiles" label="Dashboard summary" clickable @select="emit('drill', tileDrill($event, totals))" />
			<DashboardStatusCards :totals="totals" :active="filters.status" @toggle="toggleStatus" />
			<DashboardTable :rows="totals.tableRows" :ppos="data.ppos" :sewing-processes="data.sewing_processes" @drill="emit('drill', $event)" />
		</template>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Skeleton from "primevue/skeleton"
import { computed, onMounted, reactive, ref } from "vue"

import { getPlanningDashboard } from "../../../api/planning.js"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import InlinePageNavigation from "../../../components/navigation/InlinePageNavigation.vue"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import DashboardStatusCards from "./DashboardStatusCards.vue"
import DashboardTable from "./DashboardTable.vue"
import FilterMultiSelect from "./FilterMultiSelect.vue"
import SummaryTiles from "./SummaryTiles.vue"
import { formatQuantity } from "./dashboardFormat.js"
import { dashboardTiles } from "./summaryCards.js"
import { dashboardOptions, dashboardTotals, emptyDashboardFilters, hasDashboardFilter, tileDrill } from "./dashboardRows.js"

/** Factory-wide view of every open PPO and its lots; tiles, PPO and Lot links drill into PPO Tracking. */
const props = defineProps({ category: { type: Array, default: () => [] } })
const emit = defineEmits(["drill", "update:category"])
const FILTERS = [
	{ kind: "ppo", label: "PPO", placeholder: "All PPOs" },
	{ kind: "lot", label: "Lot", placeholder: "All lots" },
	{ kind: "item", label: "Item", placeholder: "All items" },
	{ kind: "product_category", label: "Product Category", placeholder: "All categories" },
	{ kind: "status", label: "Status", placeholder: "All statuses" },
]
const data = ref(null)
const loading = ref(false)
const error = ref("")
const filters = reactive(emptyDashboardFilters())
const activeFilters = computed(() => ({ ...filters, product_category: props.category }))

const ppoTotal = computed(() => Object.keys(data.value?.ppos || {}).length)
const totals = computed(() => dashboardTotals(data.value || { lots: [], ppos: {} }, activeFilters.value))
const options = computed(() => Object.fromEntries(FILTERS.map(({ kind }) => [kind, dashboardOptions(data.value?.lots || [], activeFilters.value, kind, data.value?.ppos)])))
const tiles = computed(() => dashboardTiles(totals.value))

async function load() {
	loading.value = true
	error.value = ""
	try {
		data.value = await getPlanningDashboard()
	} catch (reason) {
		error.value = reason?.message || "Unable to load the Planning Dashboard."
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

function toggleStatus(status) {
	filters.status = filters.status.length === 1 && filters.status[0] === status ? [] : [status]
}

onMounted(load)
</script>

<style scoped>
.pd-head__title { display: flex; min-width: 0; align-items: center; gap: 10px; }
.pd-head__title > div { min-width: 0; }
</style>
