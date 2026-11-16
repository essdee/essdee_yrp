<template>
	<DepartmentPage title="Time and Action Update" back-to="/planning" back-label="Planning" :show-title="false" flat full-width inline-navigation>
		<section class="ta-update erp-workspace" aria-label="Time and Action Update">
			<header class="ta-update__filters">
				<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" :show-open-button="false" show-clear />
				<LinkField v-model="filters.item" doctype="Item" label="Item" :show-open-button="false" show-clear />
				<span class="ta-update__count">{{ loading ? "Loading…" : `${rows.length} open ${rows.length === 1 ? "T&A" : "T&As"}` }}</span>
			</header>
			<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<div v-else-if="rows.length" class="erp-table-wrap ta-update__list" role="region" tabindex="0" aria-label="Open Time and Actions">
				<table class="erp-data-table">
					<thead>
						<tr>
							<th>T&A</th><th>Lot / Production Order</th><th>Item</th><th>Master</th><th class="erp-number">Qty</th>
							<th>Start Date</th><th>Expected End</th><th class="erp-number">Delay</th><th>Status</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="row in rows" :key="row.name" class="ta-update__row" :class="{ 'ta-update__row--selected': row.name === selected }" tabindex="0" :aria-selected="row.name === selected" @click="select(row.name)" @keydown.enter="select(row.name)">
							<td><strong>{{ row.name }}</strong></td>
							<td>{{ row.against_id }}</td>
							<td>{{ row.item }}</td>
							<td>{{ row.master }}</td>
							<td class="erp-number">{{ row.qty }}</td>
							<td>{{ formatDisplayDate(row.start_date, "") }}</td>
							<td>{{ formatDisplayDate(row.end_date, "") }}</td>
							<td class="erp-number">{{ row.delay }} / {{ row.rescheduled_delay }}</td>
							<td><Tag :value="row.status" :severity="row.status === 'In Progress' ? 'info' : 'secondary'" /></td>
						</tr>
					</tbody>
				</table>
			</div>
			<div v-else-if="!loading" class="erp-empty-state">
				<div><i class="pi pi-calendar-clock" /><strong>No open Time and Action</strong><span>Nothing matches the Lot and Item filters.</span></div>
			</div>
			<TimeAndActionEditor v-if="selected" :key="selected" :name="selected" @saved="load" @completed="completed" />
		</section>
	</DepartmentPage>
</template>

<script setup>
import Tag from "primevue/tag"
import { reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getOpenTimeAndActions } from "../../../api/timeAndAction.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import LinkField from "../../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import TimeAndActionEditor from "./TimeAndActionEditor.vue"

/** Open (not Completed) T&As filtered by Lot and Item; the selected one opens the Desk-style Update matrix. */
const route = useRoute()
const router = useRouter()
const filters = reactive({ lot: route.query.lot || "", item: route.query.item || "" })
const rows = ref([])
const loading = ref(false)
const loadError = ref("")
const selected = ref(route.query.time_and_action || "")
let sequence = 0

async function load() {
	const current = ++sequence
	loading.value = true
	loadError.value = ""
	try {
		const payload = await getOpenTimeAndActions(filters)
		if (current !== sequence) return
		rows.value = payload || []
		if (filters.lot && rows.value.length === 1 && !selected.value) select(rows.value[0].name)
	} catch (reason) {
		if (current === sequence) loadError.value = reason?.message || "Unable to load open Time and Actions."
	} finally {
		if (current === sequence) loading.value = false
	}
}

function select(name) {
	selected.value = name
	router.replace({ query: { ...route.query, time_and_action: name } })
}

function completed() {
	selected.value = ""
	router.replace({ query: { lot: filters.lot || undefined, item: filters.item || undefined } })
	load()
}

watch(() => [filters.lot, filters.item], () => {
	selected.value = ""
	router.replace({ query: { lot: filters.lot || undefined, item: filters.item || undefined } })
	load()
})
load()
</script>

<style scoped>
.ta-update { display: grid; width: 100%; min-width: 0; gap: var(--erp-space-4); padding: var(--erp-space-2) 0 var(--erp-space-5); }
.ta-update__filters { display: flex; flex-wrap: wrap; gap: var(--erp-space-3); align-items: flex-end; }
.ta-update__filters > :deep(.common-field) { width: min(280px, 100%); }
.ta-update__count { color: var(--erp-text-muted); padding-bottom: var(--erp-space-2); }
.ta-update__list { max-height: 40vh; overflow: auto; }
.ta-update__row { cursor: pointer; }
.ta-update__row--selected td { background: var(--erp-accent-soft); }
</style>
