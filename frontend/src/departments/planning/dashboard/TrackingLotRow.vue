<template>
	<tr class="pd-lot-row" :class="{ 'is-open': open, 'is-dispatched': row.status === 'Dispatched' }" :data-lot-row="row.lot" @click="emit('toggle')">
		<td><button type="button" class="pd-caret-button" :aria-expanded="open" :aria-label="`${open ? 'Collapse' : 'Expand'} ${row.lot}`" @click.stop="emit('toggle')"><i class="pi pi-chevron-right pd-caret" :class="{ 'is-open': open }" aria-hidden="true" /></button></td>
		<td class="pd-nowrap">
			<span class="pd-lot-cell">
				<span class="pd-lot-name">
					<router-link class="pd-link" :to="`/planning/lots/${encodeURIComponent(row.lot)}`" @click.stop>{{ row.lot }}</router-link>
					<span v-if="!ppoItems.includes(row.item)" class="pd-item-note" title="Lot item differs from the PPO item">{{ row.item }}</span>
				</span>
				<LotPlanShortcutButtons :lot="row.lot" :access="planAccess" compact />
			</span>
		</td>
		<td><LotStatusPill :status="row.status" /></td>
		<td class="pd-nowrap">{{ delivery.date }}<template v-if="delivery.lateDays"> · <span class="pd-late" :title="`${delivery.lateDays} days past delivery`">{{ delivery.lateDays }}d late</span></template></td>
		<td />
		<td class="pd-number" data-col="lot">{{ formatQuantity(row.qty) }}</td>
		<td class="pd-number" data-col="cut">{{ formatQuantity(row.cut_pcs) }}</td>
		<td class="pd-number" data-col="dispatch">{{ formatQuantity(row.dispatch) }}</td>
		<td class="pd-number" data-col="balance" :class="{ 'is-negative': row.balance < 0 }" :title="`${row.cut ? 'Cut' : 'Lot'} pcs ${formatQuantity(row.total)} − Dispatch ${formatQuantity(row.dispatch)}`">{{ formatQuantity(row.balance) }}</td>
		<td class="pd-progress-cell">
			<span class="pd-strip" role="img" :aria-label="`${strip.done} of ${strip.total} processes completed`">
				<span v-for="segment in strip.segments" :key="segment.name" class="pd-seg" :class="`pd-seg--${segment.status}`" :title="segment.tip" />
			</span>
			<span class="pd-strip-label" :title="`${strip.current}: latest process with activity · ${strip.done} of ${strip.total} processes completed`"><b>{{ strip.done }} of {{ strip.total }} done</b> · {{ strip.current }}</span>
		</td>
	</tr>
</template>

<script setup>
import { computed } from "vue"

import LotPlanShortcutButtons from "../lot/LotPlanShortcutButtons.vue"
import LotStatusPill from "./LotStatusPill.vue"
import { deliveryParts, formatQuantity } from "./dashboardFormat.js"
import { progressStrip } from "./trackingRows.js"

/** One lot: CCR / OCR shortcuts, status, delivery against the data date, quantities and the process progress strip. */
const props = defineProps({
	row: { type: Object, required: true },
	ppoItems: { type: Array, default: () => [] },
	asOf: { type: String, default: "" },
	planAccess: { type: Object, default: () => ({}) },
	open: Boolean,
})
const emit = defineEmits(["toggle"])
const strip = computed(() => progressStrip(props.row))
const delivery = computed(() => deliveryParts(props.row.delivery, props.asOf))
</script>

<style scoped>
.pd-lot-cell { display: flex; align-items: center; gap: 6px; min-width: 0; }
.pd-lot-name { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
</style>
