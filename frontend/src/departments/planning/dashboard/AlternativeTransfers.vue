<template>
	<div v-if="transfers.length" class="pd-alt" data-alternatives>
		<b class="pd-alt__title">Moved to alternative · {{ formatQuantity(total) }} pcs<small>counted as dispatched</small></b>
		<ul>
			<li v-for="transfer in transfers" :key="`${transfer.lot}-${transfer.work_order}`" :data-alternative-lot="transfer.lot">
				<span>{{ transfer.item }}</span>
				<b>{{ formatQuantity(transfer.quantity) }} pcs</b>
				<span v-if="transfer.boxes !== null && transfer.boxes !== undefined" class="pd-muted">{{ formatQuantity(transfer.boxes, true) }} box</span>
				<span class="pd-muted">→</span>
				<router-link class="pd-link" :to="`/planning/lots/${encodeURIComponent(transfer.lot)}`" @click.stop>{{ transfer.lot }}</router-link>
				<router-link v-if="showWorkOrder" class="pd-link pd-muted" :to="`/planning/work-orders/${encodeURIComponent(transfer.work_order)}`" @click.stop>{{ transfer.work_order }}</router-link>
			</li>
		</ul>
	</div>
</template>

<script setup>
import { computed } from "vue"

import { formatQuantity } from "./dashboardFormat.js"

/** One line per alternative lot a lot's pieces were moved to: item, pieces, boxes and the lot link. */
const props = defineProps({
	transfers: { type: Array, default: () => [] },
	showWorkOrder: { type: Boolean, default: false },
})
const total = computed(() => props.transfers.reduce((sum, transfer) => sum + (Number(transfer.quantity) || 0), 0))
</script>

<style>
.pd-alt { display: grid; gap: 4px; padding: 6px 10px; font-size: 12px; border: 1px solid var(--erp-border); border-left: 3px solid var(--erp-warning, #d97706); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.pd-alt__title { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; }
.pd-alt__title small { color: var(--erp-text-muted); font-weight: 500; }
.pd-alt ul { display: grid; gap: 2px; margin: 0; padding: 0; list-style: none; }
.pd-drill__alt { margin: 0 0 8px; }
.pd-alt li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 8px; }
</style>
