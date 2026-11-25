<template>
	<Dialog v-model:visible="visible" modal header="Work Order already created" class="erp-dialog--lg">
		<div class="work-order-duplicates" role="status">
			<p>A Work Order was already created against this Supplier for the same Lot, Item and Process.</p>
			<div class="erp-table-wrap work-order-duplicates__table">
				<table class="erp-data-table">
					<thead>
						<tr><th>Work Order</th><th>Date</th><th>Status</th><th class="is-number">Planned</th><th class="is-number">Delivered</th><th class="is-number">Received</th><th>Created By</th></tr>
					</thead>
					<tbody>
						<tr v-for="row in rows" :key="row.name">
							<td class="is-nowrap"><DocumentLink doctype="YRP Work Order" :name="row.name" @click="visible = false" /></td>
							<td class="is-nowrap">{{ formatDisplayDate(row.wo_date) }}</td>
							<td>{{ row.status }}</td>
							<td class="is-number">{{ formatQuantity(row.planned_quantity) }}</td>
							<td class="is-number">{{ formatQuantity(row.total_no_of_pieces_delivered) }}</td>
							<td class="is-number">{{ formatQuantity(row.total_no_of_pieces_received) }}</td>
							<td>{{ row.created_by }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>
		<template #footer><Button label="Close" autofocus @click="visible = false" /></template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import { ref } from "vue"

import { getDuplicateWorkOrders } from "../../api/fabricStore.js"
import DocumentLink from "../../components/common/DocumentLink.vue"
import { formatDisplayDate } from "../../utils/dateFormat.js"

/** Informational notice listing other submitted Work Orders for the same lot, item, supplier and process. */
const visible = ref(false)
const rows = ref([])
const quantity = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 })

function formatQuantity(value) { return quantity.format(Number(value) || 0) }

async function check(workOrder) {
	if (!workOrder) return
	try { rows.value = await getDuplicateWorkOrders(workOrder) || [] }
	catch { rows.value = [] }
	visible.value = rows.value.length > 0
}

defineExpose({ check })
</script>

<style scoped>
.work-order-duplicates p { margin: 0 0 var(--erp-space-3); }
.work-order-duplicates__table { max-height: 50vh; overflow: auto; }
.work-order-duplicates .is-number { text-align: right; }
.work-order-duplicates .is-nowrap { white-space: nowrap; }
</style>
