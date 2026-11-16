<template>
	<div class="lot-tab-stack">
		<Skeleton v-if="loading" height="240px" />
		<Message v-else-if="error || loadError" severity="error" :closable="false">{{ error || loadError }}</Message>
		<LotEmptyState v-else-if="!timeAndAction" title="No Time and Action yet" reason="Use Create T&A to plan this Lot's actions." />
		<section v-else-if="data" class="lot-group">
			<header class="lot-group__header">
				<strong>Time and Action</strong>
				<span><DocumentLink doctype="SD YRP Time and Action" :name="data.name" /> · {{ data.master }} · {{ data.status }}</span>
				<RouterLink v-if="data.status !== 'Completed'" :to="{ name: PLANNING_ROUTES.timeAndActionUpdate, query: { lot, time_and_action: data.name } }" class="ta-report__update">Update T&A</RouterLink>
			</header>
			<div class="erp-table-wrap lot-table-wrap" role="region" tabindex="0" aria-label="Time and Action report">
				<table class="erp-data-table lot-table">
					<thead><tr><th v-for="column in REPORT_COLUMNS" :key="column.key" :class="{ 'erp-number': column.number }">{{ column.label }}</th></tr></thead>
					<tbody>
						<tr v-for="row in data.rows" :key="row.action">
							<td v-for="column in REPORT_COLUMNS" :key="column.key" :class="{ 'erp-number': column.number, [`ta-report__actual--${actualTone(row)}`]: column.key === 'actual_date' }">{{ reportCell(row, column) }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</section>
	</div>
</template>

<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { ref, watch } from "vue"

import { getUpdateData } from "../../../api/timeAndAction.js"
import DocumentLink from "../../../components/common/DocumentLink.vue"
import LotEmptyState from "../lot/LotEmptyState.vue"
import { PLANNING_ROUTES } from "../planningRoutes.js"
import { REPORT_COLUMNS, actualTone, reportCell } from "./timeAndAction.js"

/** Read-only Time and Action report of one Lot, the Desk Lot report columns without Complete T&A. */
const props = defineProps({ lot: { type: String, required: true }, timeAndAction: { type: String, default: "" }, loadError: { type: String, default: "" } })
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
.ta-report__update { margin-left: auto; font-weight: 600; }
.ta-report__actual--late { background: var(--erp-danger-soft); }
.ta-report__actual--on-time { background: var(--erp-success-soft); }
</style>
