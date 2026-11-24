<template>
	<section class="ipd-approval__card is-wide ipd-approval-wo" :class="{ 'is-warning': affectedCount }" data-testid="ipd-approval-work-orders">
		<header>
			<h3>Work Orders submitted</h3>
			<span class="ipd-approval__tag">{{ orders.length }} {{ orders.length === 1 ? "Work Order" : "Work Orders" }}</span>
			<span v-if="affectedCount" class="ipd-approval__tag is-warning">{{ affectedCount }} in changed processes</span>
		</header>
		<div v-if="changedProcesses.length" class="ipd-approval-wo__changes">
			<p v-for="entry in changedProcesses" :key="entry.process">
				<strong>{{ entry.process }}</strong> changed since the last approval:
				<span>{{ entry.changes.slice(0, 4).join(" · ") }}</span>
				<span v-if="entry.changes.length > 4" class="ipd-approval__subtle">+{{ entry.changes.length - 4 }} more</span>
			</p>
		</div>
		<p v-if="!orders.length" class="ipd-approval__empty">No submitted Work Orders</p>
		<div v-for="group in groups" :key="group.process" class="ipd-approval-wo__group" :class="{ 'is-affected': group.isAffected }">
			<div class="ipd-approval-wo__process">
				<strong>{{ group.process }}</strong>
				<span class="ipd-approval__subtle">{{ group.orders.length }}</span>
				<span v-if="group.isAffected" class="ipd-approval__tag is-warning">Review: cancel and recreate if needed</span>
			</div>
			<div class="ipd-approval-wo__row">
				<article
					v-for="order in group.orders"
					:key="order.name"
					class="ipd-approval-wo__order"
					:class="{ 'is-affected': order.is_affected }"
					tabindex="0"
					@mouseenter="showCard($event.currentTarget, order)"
					@mouseleave="scheduleHide"
					@focusin="showCard($event.currentTarget, order)"
					@focusout="scheduleHide"
				>
					<header>
						<strong><DocumentLink doctype="YRP Work Order" :name="order.name" /></strong>
						<span v-if="order.open_status === 'Close'" class="ipd-approval__tag">Closed</span>
					</header>
					<span class="ipd-approval-wo__supplier">{{ order.supplier_name || order.supplier }}</span>
					<table v-if="order.grid.total" class="ipd-approval-wo__grid">
						<thead>
							<tr><th /><th v-for="size in order.grid.sizes" :key="size">{{ size || "Qty" }}</th></tr>
						</thead>
						<tbody>
							<tr v-for="(colour, index) in order.grid.colours" :key="colour">
								<th>{{ colour || "—" }}</th>
								<td v-for="(cell, cellIndex) in order.grid.cells[index]" :key="cellIndex">{{ cell == null ? "" : quantity(cell) }}</td>
							</tr>
						</tbody>
					</table>
					<span v-else class="ipd-approval__subtle">No {{ workOrders.colour_attribute.toLowerCase() }} × {{ workOrders.size_attribute.toLowerCase() }} quantities</span>
					<footer>Total {{ quantity(order.grid.total) }}</footer>
				</article>
			</div>
		</div>
		<Popover ref="popover" class="ipd-approval-wo__popover" :dismissable="false">
			<div v-if="active" class="ipd-approval-wo__card" @mouseenter="cancelHide" @mouseleave="scheduleHide">
				<strong>{{ active.name }}</strong>
				<dl>
					<dt>Process</dt><dd>{{ active.process_name }}{{ active.is_rework ? " (rework)" : "" }}</dd>
					<dt>Supplier</dt><dd>{{ active.supplier_name || active.supplier }}</dd>
					<dt>Lot</dt><dd>{{ active.lot || "—" }}</dd>
					<dt>Date</dt><dd>{{ formatDisplayDate(active.wo_date) }}</dd>
					<dt>Status</dt><dd>{{ active.open_status === "Close" ? "Closed" : "Open" }}</dd>
					<dt>Planned</dt><dd>{{ quantity(active.planned_quantity) }}</dd>
				</dl>
				<p v-if="active.is_affected" class="ipd-approval-wo__note">{{ active.process_name }} changed since the last approval. Cancel and recreate this Work Order if it needs the change.</p>
			</div>
		</Popover>
	</section>
</template>

<script setup>
import Popover from "primevue/popover"
import { computed, nextTick, onBeforeUnmount, ref } from "vue"

import DocumentLink from "../../../../components/common/DocumentLink.vue"
import { formatDisplayDate } from "../../../../utils/dateFormat.js"
import { quantity, workOrderGroups } from "./ipdApproval.js"

/** Submitted Work Orders of the IPD's lots, grouped by process; changed processes come first. */
const props = defineProps({
	workOrders: { type: Object, default: () => ({ orders: [], changes: { processes: [] }, colour_attribute: "Colour", size_attribute: "Size" }) },
})
const orders = computed(() => props.workOrders.orders || [])
const changedProcesses = computed(() => props.workOrders.changes?.processes || [])
const groups = computed(() => workOrderGroups(orders.value))
const affectedCount = computed(() => orders.value.filter((order) => order.is_affected).length)
const popover = ref(null)
const active = ref(null)
let showTimer = null
let hideTimer = null

function cancelHide() {
	clearTimeout(hideTimer)
}
function scheduleHide() {
	clearTimeout(showTimer)
	hideTimer = setTimeout(() => popover.value?.hide(), 150)
}
function showCard(target, order) {
	cancelHide()
	clearTimeout(showTimer)
	showTimer = setTimeout(async () => {
		const moving = active.value && active.value.name !== order.name
		active.value = order
		if (moving) {
			popover.value?.hide()
			await nextTick()
		}
		popover.value?.show({ currentTarget: target }, target)
	}, 250)
}

onBeforeUnmount(() => {
	clearTimeout(showTimer)
	clearTimeout(hideTimer)
})
</script>
