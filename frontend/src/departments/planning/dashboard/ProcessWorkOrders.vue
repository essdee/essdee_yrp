<template>
	<div class="pd-detail__section">
		<h4 v-if="!compact">Work Orders</h4>
		<table class="erp-data-table pf-table">
			<thead>
				<tr>
					<th>Work Order</th><th>Supplier</th><th>Status</th>
					<template v-if="!compact"><th>First DC</th><th>Last GRN</th></template>
					<th v-if="!compact" class="erp-number">Planned {{ isCloth ? "Kg" : "pcs" }}</th>
					<th class="erp-number">Delivered {{ isCloth || step.kind === "cutting" ? "Kg" : "pcs" }}</th>
					<th class="erp-number">Received {{ isCloth ? "Kg" : "pcs" }}</th>
					<th v-if="compact" class="erp-number">Pending {{ isCloth ? "Kg" : "pcs" }}</th>
				</tr>
			</thead>
			<tbody>
				<tr v-for="order in workOrders" :key="order.name">
					<td><router-link class="pd-link" :to="`/planning/work-orders/${encodeURIComponent(order.name)}`">{{ order.name }}</router-link></td>
					<td>{{ order.supplier_name || order.supplier }}</td>
					<td><span class="pd-state" :class="`pd-state--${orderTone(order)}`">{{ order.status }}</span></td>
					<template v-if="!compact">
						<td>{{ formatDisplayDate(order.first_dc) }}</td>
						<td>{{ formatDisplayDate(order.last_grn) }}</td>
						<td class="erp-number">{{ formatQuantity(order.planned, isCloth) }}</td>
					</template>
					<td class="erp-number">{{ formatQuantity(order.delivered, isCloth || step.kind === "cutting") }}</td>
					<td class="erp-number">{{ formatQuantity(order.received, isCloth) }}</td>
					<td v-if="compact" class="erp-number">{{ formatQuantity(pendingQuantity(order), isCloth) }}</td>
				</tr>
			</tbody>
		</table>
	</div>
</template>

<script setup>
import { computed } from "vue"

import { formatDisplayDate } from "../../../utils/dateFormat.js"
import { formatQuantity } from "./dashboardFormat.js"
import { pendingQuantity } from "./trackingRows.js"

/** Work Orders of one lot process with their dates and quantities; `compact` drops dates and planned for pending. */
const props = defineProps({
	step: { type: Object, required: true },
	workOrders: { type: Array, default: () => [] },
	compact: { type: Boolean, default: false },
})
const DONE = ["Fully Received", "Partially Billed", "Fully Billed", "Close Request", "Closed"]
const PARTIAL = ["Partially Delivered", "Fully Delivered", "Partially Received"]
const isCloth = computed(() => props.step.kind === "cloth")
const orderTone = (order) => (DONE.includes(order.status) ? "done" : PARTIAL.includes(order.status) ? "partial" : "idle")
</script>
