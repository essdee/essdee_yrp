<template>
	<DepartmentPage title="Time and Action Update" back-to="/planning" back-label="Planning" flat full-width inline-navigation>
		<section class="ta-update erp-workspace" aria-label="Time and Action Update">
			<header class="ta-update__filters">
				<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" :show-open-button="false" show-clear />
				<LinkField v-model="filters.item" doctype="Item" label="Item" :show-open-button="false" show-clear />
				<span class="ta-update__count">{{ countLabel }}</span>
			</header>
			<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<div v-else-if="rows.length" class="ta-update__card">
				<table class="erp-data-table ta-list">
					<thead>
						<tr>
							<th class="ta-list__chev" aria-hidden="true" /><th>T&A</th><th>Against</th><th>Against ID</th><th>Item</th><th>Start Date</th>
							<th>Expected Delivery</th><th>Progress</th><th>Next Action</th><th>Running Delay</th><th>Status</th>
						</tr>
					</thead>
					<tbody>
						<template v-for="row in rows" :key="row.name">
							<tr class="ta-list__row" :class="{ 'is-open': row.name === expanded }" tabindex="0" :aria-expanded="row.name === expanded" @click="toggle(row.name)" @keydown.enter.self="toggle(row.name)">
								<td class="ta-list__chev"><i class="pi pi-chevron-down" aria-hidden="true" /></td>
								<td class="ta-list__nowrap"><strong>{{ row.name }}</strong><span v-if="row.name === expanded" class="ta-list__open-tag">Open</span></td>
								<td class="ta-list__nowrap">{{ againstLabel(row.against) }}</td>
								<td class="ta-list__nowrap">{{ row.against_id }}</td>
								<td>{{ row.item }}</td>
								<td>{{ formatDisplayDate(row.start_date, "") }}</td>
								<td>{{ formatDisplayDate(row.end_date, "") }}</td>
								<td class="ta-list__nowrap">{{ row.dated }} of {{ row.total }} dated</td>
								<td>
									<div v-if="row.next_action" class="ta-list__next"><span>{{ row.next_action }}</span><TimeAndActionChip v-bind="getNextActionChip(row)" /></div>
									<span v-else class="ta-list__subtle">All dated</span>
								</td>
								<td class="ta-list__nowrap"><b class="ta-list__delay" :class="`ta-list__delay--${getRunningDelay(row.delay).tone}`">{{ getRunningDelay(row.delay).text }}</b></td>
								<td><TimeAndActionChip tone="info" :label="row.status" /></td>
							</tr>
							<tr v-if="row.name === expanded" class="ta-list__expand">
								<td colspan="11"><TimeAndActionEditor :name="row.name" @dirty="dirty = $event" @saved="load" @completed="completed" /></td>
							</tr>
						</template>
					</tbody>
				</table>
			</div>
			<div v-else-if="!loading" class="erp-empty-state">
				<div><i class="pi pi-calendar-clock" /><strong>No open Time and Action</strong><span>Nothing matches the Lot and Item filters.</span></div>
			</div>
		</section>
		<DocumentConfirmationDialog v-model:visible="discardVisible" :title="`Discard changes to ${expanded}?`" :message="discardMessage" confirm-label="Discard changes" cancel-label="Keep editing" @confirm="confirmDiscard" />
	</DepartmentPage>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getOpenTimeAndActions } from "../../../api/timeAndAction.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import LinkField from "../../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import TimeAndActionChip from "./TimeAndActionChip.vue"
import TimeAndActionEditor from "./TimeAndActionEditor.vue"
import { againstLabel, getNextActionChip, getRunningDelay } from "./timeAndAction.js"

/** Accordion of open (not Completed) T&As filtered by Lot and Item; one opens inline at a time for updating. */
const route = useRoute()
const router = useRouter()
const filters = reactive({ lot: route.query.lot || "", item: route.query.item || "" })
const rows = ref([])
const loading = ref(false)
const loadError = ref("")
const expanded = ref(route.query.time_and_action || "")
const dirty = ref(0)
const discardVisible = ref(false)
const pendingTarget = ref("")
let sequence = 0

const countLabel = computed(() => {
	if (loading.value && !rows.value.length) return "Loading…"
	return `${rows.value.length} open ${rows.value.length === 1 ? "T&A" : "T&As"} · click one to update it`
})
const discardMessage = computed(() => {
	const count = dirty.value
	const them = count === 1 ? "it" : "them"
	const effect = pendingTarget.value ? `Opening ${pendingTarget.value} discards ${them}.` : `Closing it discards ${them}.`
	return `${expanded.value} has ${count} unsaved ${count === 1 ? "change" : "changes"}. ${effect}`
})

async function load() {
	const current = ++sequence
	loading.value = true
	loadError.value = ""
	try {
		const payload = await getOpenTimeAndActions(filters)
		if (current !== sequence) return
		rows.value = payload || []
		if (filters.lot && rows.value.length === 1 && !expanded.value) open(rows.value[0].name)
	} catch (reason) {
		if (current === sequence) loadError.value = reason?.message || "Unable to load open Time and Actions."
	} finally {
		if (current === sequence) loading.value = false
	}
}

function open(name) {
	expanded.value = name
	dirty.value = 0
	router.replace({ query: { ...route.query, time_and_action: name || undefined } })
	if (name) nextTick(() => document.querySelector(".ta-list__row.is-open")?.scrollIntoView({ block: "start", behavior: "smooth" }))
}

function toggle(name) {
	const target = expanded.value === name ? "" : name
	if (dirty.value) {
		pendingTarget.value = target
		discardVisible.value = true
		return
	}
	open(target)
}

function confirmDiscard() {
	discardVisible.value = false
	open(pendingTarget.value)
}

function completed() {
	open("")
	load()
}

watch(() => [filters.lot, filters.item], () => {
	expanded.value = ""
	dirty.value = 0
	router.replace({ query: { lot: filters.lot || undefined, item: filters.item || undefined } })
	load()
})
load()
</script>

<style scoped>
.ta-update { display: grid; width: 100%; min-width: 0; gap: var(--erp-space-3); padding: var(--erp-space-2) 0 var(--erp-space-5); }
.ta-update__filters { display: flex; flex-wrap: wrap; gap: var(--erp-space-3); align-items: flex-end; }
.ta-update__filters > :deep(.common-field) { width: min(280px, 100%); }
.ta-update__count { padding-bottom: 9px; color: var(--erp-text-muted); }
.ta-update__card { min-width: 0; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-radius-md); }
.ta-list > thead th { position: static; }
.ta-list > thead th:first-child { border-top-left-radius: var(--erp-radius-md); }
.ta-list > thead th:last-child { border-top-right-radius: var(--erp-radius-md); }
.ta-list > tbody > tr.ta-list__row { cursor: pointer; }
.ta-list > tbody > tr.ta-list__row:hover > td { background: var(--erp-accent-soft); }
.ta-list > tbody > tr.ta-list__row.is-open > td { font-weight: 600; color: var(--erp-text); background: var(--erp-accent-soft); border-bottom: 0; }
.ta-list > tbody > tr.ta-list__row.is-open > td:first-child { box-shadow: inset 3px 0 0 var(--erp-accent); }
.ta-list__nowrap { white-space: nowrap; }
.ta-list__delay--late { color: var(--erp-danger); }
.ta-list__delay--ok { color: var(--erp-success-text); }
.ta-list__delay--none { color: var(--erp-text-muted); }
.ta-list__chev { width: 36px; padding-right: 0 !important; color: var(--erp-text-muted); }
.ta-list__chev i { font-size: 12px; transition: transform 160ms ease; }
.ta-list tr.is-open .ta-list__chev i { color: var(--erp-accent); transform: rotate(180deg); }
.ta-list__next { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; font-size: var(--erp-font-size-caption); }
.ta-list__subtle { color: var(--erp-text-subtle); }
.ta-list__open-tag { display: inline-flex; margin-left: 8px; padding: 1px 7px; color: var(--erp-on-accent); font-size: var(--erp-font-size-min); font-weight: 700; letter-spacing: .06em; text-transform: uppercase; vertical-align: 1px; background: var(--erp-accent); border-radius: 4px; }
.ta-list > tbody > tr.ta-list__expand > td,
.ta-list > tbody > tr.ta-list__expand:hover > td { padding: 4px 0 0; background: var(--erp-surface-muted); border-bottom: 1px solid var(--erp-border-strong); box-shadow: inset 3px 0 0 var(--erp-accent), inset 0 8px 10px -8px rgba(0, 0, 0, .18); }
@media (prefers-reduced-motion: reduce) { .ta-list__chev i { transition: none; } }
</style>
