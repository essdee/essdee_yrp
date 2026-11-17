<template>
	<div class="lot-tab-stack">
		<Skeleton v-if="loading" height="240px" />
		<Message v-else-if="error || loadError" severity="error" :closable="false">{{ error || loadError }}</Message>
		<div v-else-if="!timeAndAction" class="erp-empty-state lot-empty">
			<div>
				<i class="pi pi-calendar" />
				<strong>No Time and Action for this {{ subject }}</strong>
				<span>Create one from an Action Master to plan every step up to dispatch.</span>
				<Button v-if="canCreate" label="Create T&A" icon="pi pi-plus" size="small" class="ta-report__create" @click="emit('create')" />
				<Message v-else-if="createBlockedReason === 'no_assigned_person'" severity="warn" :closable="false" class="ta-report__create">Please set the Assigned Person to create T&A.</Message>
				<Message v-else-if="createBlockedReason === 'linked_lots'" severity="warn" :closable="false" class="ta-report__create">Lots are linked to this Production Order. Create the T&A from the Lot.</Message>
			</div>
		</div>
		<section v-else-if="data" class="ta-report" aria-label="Time and Action">
			<div class="ta-report__summary">
				<dl class="ta-report__facts">
					<div><dt>T&A</dt><dd data-ta-name>{{ data.name }}</dd></div>
					<div><dt>Master</dt><dd>{{ data.master }}</dd></div>
					<div><dt>Start Date</dt><dd>{{ formatDisplayDate(data.start_date, "") }}</dd></div>
					<div><dt>Expected Delivery</dt><dd>{{ formatDisplayDate(data.end_date, "") }}</dd></div>
					<div><dt>Status</dt><dd><TimeAndActionChip tone="info" :label="data.status" /></dd></div>
				</dl>
				<div class="ta-report__actions">
					<slot name="actions" :data="data" />
					<RevertTimeAndActionButton :data="data" @reverted="emit('reverted', $event)" />
					<RouterLink v-if="data.status === 'In Progress' && data.can_update_dates" v-slot="{ navigate, href }" custom :to="{ name: updateRouteName, query: { lot: lot || undefined, ta: data.name } }">
						<Button as="a" :href="href" label="Update dates" icon="pi pi-calendar" severity="secondary" outlined size="small" @click="navigate" />
					</RouterLink>
				</div>
			</div>
			<div class="erp-table-wrap lot-table-wrap" role="region" tabindex="0" aria-label="Time and Action report">
				<table class="erp-data-table lot-table ta-report__table">
					<thead><tr><th v-for="column in REPORT_COLUMNS" :key="column.key" :class="{ 'erp-number': column.number }">{{ column.label }}</th></tr></thead>
					<tbody>
						<tr v-for="row in data.rows" :key="row.action">
							<td v-for="column in REPORT_COLUMNS" :key="column.key" :class="[{ 'erp-number': column.number, 'ta-report__action': column.key === 'action' }, reportTone(row, column) && `ta-report--${reportTone(row, column)}`]">{{ reportCell(row, column) }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</section>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { ref, watch } from "vue"

import { getUpdateData } from "../../../api/timeAndAction.js"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import { PLANNING_ROUTES } from "../planningRoutes.js"
import RevertTimeAndActionButton from "./RevertTimeAndActionButton.vue"
import TimeAndActionChip from "./TimeAndActionChip.vue"
import { REPORT_COLUMNS, reportCell, reportTone } from "./timeAndAction.js"

/** Read-only Time and Action of one Lot or Production Order: summary facts and the Desk Lot report columns. */
const props = defineProps({
	lot: { type: String, default: "" },
	subject: { type: String, default: "Lot" },
	timeAndAction: { type: String, default: "" },
	loadError: { type: String, default: "" },
	canCreate: { type: Boolean, default: false },
	createBlockedReason: { type: String, default: "" },
	updateRouteName: { type: String, default: PLANNING_ROUTES.timeAndActionUpdate },
})
const emit = defineEmits(["create", "reverted"])
const data = ref(null)
const loading = ref(false)
const error = ref("")

async function load() {
	data.value = null
	error.value = ""
	if (!props.timeAndAction) return
	loading.value = true
	try {
		data.value = await getUpdateData(props.timeAndAction)
	} catch (reason) {
		error.value = reason?.message || "Unable to load the Time and Action."
	} finally {
		loading.value = false
	}
}

watch(() => props.timeAndAction, load, { immediate: true })
</script>

<style scoped>
.ta-report__create { margin-top: var(--erp-space-2); }
.ta-report { display: grid; min-width: 0; gap: var(--erp-space-3); }
.ta-report__summary { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px 16px; }
.ta-report__actions { display: flex; flex-wrap: wrap; gap: 8px; }
.ta-report__facts { display: flex; flex-wrap: wrap; gap: 6px 22px; margin: 0; }
.ta-report__facts div { display: flex; flex-direction: column; }
.ta-report__facts dt { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
.ta-report__facts dd { margin: 0; font-weight: 600; font-variant-numeric: tabular-nums; }
.ta-report__table th { white-space: normal; line-height: 1.25; vertical-align: bottom; }
.ta-report__table td:nth-child(n+5):nth-child(-n+8) { white-space: nowrap; }
.ta-report__table th, .ta-report__table td { padding: 9px 10px; }
.ta-report__action { min-width: 170px; white-space: normal !important; font-weight: 600; color: var(--erp-text) !important; }
.ta-report--neg { color: var(--erp-danger) !important; font-weight: 600; }
.ta-report--pos { color: var(--erp-success-text) !important; font-weight: 600; }
</style>
