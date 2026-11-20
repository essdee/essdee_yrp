<template>
	<header class="ta-head">
		<div class="ta-head__facts">
			<div class="ta-head__title">
				<h2><span class="ta-head__kind">{{ againstShortLabel(data.against) }}</span> {{ data.against_id }}</h2>
				<span class="ta-head__item">{{ data.item }}</span>
				<TimeAndActionChip tone="info" :label="data.status" />
				<span class="ta-head__name" title="T&A ID">{{ data.name }}</span>
			</div>
			<div class="ta-head__dates">
				<span>Start: <strong>{{ formatDisplayDate(data.start_date, "") }}</strong></span>
				<span>Expected Delivery: <strong>{{ formatDisplayDate(data.end_date, "") }}</strong></span>
				<span>{{ datedCount }} of {{ total }} dated</span>
				<b class="ta-head__running" :class="`ta-head__running--${runningDelay.tone}`" title="Running delay: last action's Planned Date vs its Rescheduled or Actual Date, in working days">{{ runningDelay.text }}</b>
			</div>
		</div>
		<div class="ta-head__actions">
			<div class="ta-head__buttons">
				<Button v-tooltip.left="{ value: REVISE_HELP, class: 'ta-head__tooltip' }" icon="pi pi-info-circle" text rounded severity="secondary" size="small" aria-label="What Revise Dates does" />
				<Button label="Revise Dates" icon="pi pi-refresh" severity="secondary" outlined size="small" :disabled="busy || !data.can_revise" :title="data.can_revise ? 'Make the current Rescheduled Dates the new Freeze Dates' : 'Only the revised-date approver can revise, a limited number of times'" @click="emit('revise')" />
				<Button v-if="data.can_edit_steps" label="Update Action" icon="pi pi-list" severity="secondary" outlined size="small" :disabled="busy || unsavedCount > 0" :title="unsavedCount ? 'Save or discard your date changes first' : 'Add or remove actions'" @click="emit('steps')" />
				<Button v-if="data.can_split" label="Split T&A" icon="pi pi-clone" severity="secondary" outlined size="small" :disabled="busy" title="Copy this T&A to other Lots; it continues here" @click="emit('split')" />
				<Button v-if="data.can_view_lot_detail" label="Lot Detail" icon="pi pi-box" severity="secondary" outlined size="small" title="Cutting and process-wise delivered and received pieces, as in PPO Tracking" @click="emit('lot-detail')" />
				<Button label="Complete T&A" icon="pi pi-check" size="small" :disabled="busy || !data.can_complete || hasErrors" @click="emit('complete')" />
				<RevertTimeAndActionButton :data="data" :disabled="busy" @reverted="emit('reverted', $event)" />
			</div>
			<span class="ta-head__hint">{{ data.can_complete ? `All ${total} actions are dated` : `Complete unlocks when every action is dated · ${total - datedCount} left` }}</span>
		</div>
	</header>
</template>

<script setup>
import Button from "primevue/button"
import Tooltip from "primevue/tooltip"
import { computed } from "vue"

import { formatDisplayDate } from "../../../utils/dateFormat.js"
import RevertTimeAndActionButton from "./RevertTimeAndActionButton.vue"
import TimeAndActionChip from "./TimeAndActionChip.vue"
import { REVISE_HELP, againstShortLabel, getRunningDelay } from "./timeAndAction.js"

/** Cockpit header of one T&A: identity, dates, running delay and the T&A-level buttons. */
const props = defineProps({
	data: { type: Object, required: true },
	total: { type: Number, required: true },
	datedCount: { type: Number, required: true },
	unsavedCount: { type: Number, default: 0 },
	hasErrors: { type: Boolean, default: false },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["revise", "steps", "split", "lot-detail", "complete", "reverted"])
const vTooltip = Tooltip
const runningDelay = computed(() => getRunningDelay(props.data.delay))
</script>

<style scoped>
.ta-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 12px 20px; padding-bottom: 14px; border-bottom: 1px solid var(--erp-border); }
.ta-head__facts { display: grid; min-width: 0; gap: 8px; }
.ta-head__title { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
.ta-head__title h2 { margin: 0; font-size: var(--erp-font-size-hero); font-weight: 700; overflow-wrap: anywhere; }
.ta-head__kind { color: var(--erp-text-muted); font-size: 13px; font-weight: 600; }
.ta-head__item { color: var(--erp-text-secondary); font-size: 14px; font-weight: 600; }
.ta-head__name { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-variant-numeric: tabular-nums; }
.ta-head__dates { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 18px; color: var(--erp-text-muted); font-size: 13px; }
.ta-head__dates strong { color: var(--erp-text); font-variant-numeric: tabular-nums; }
.ta-head__running { font-size: 14px; font-weight: 700; }
.ta-head__running--late { color: var(--erp-danger); }
.ta-head__running--ok { color: var(--erp-success-text); }
.ta-head__running--none { color: var(--erp-text-muted); }
.ta-head__actions { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; margin-left: auto; }
.ta-head__buttons { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 8px; }
.ta-head__hint { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
@media (max-width: 900px) {
	.ta-head__actions { align-items: stretch; margin-left: 0; }
	.ta-head__buttons { justify-content: flex-start; }
}
@media (max-width: 640px) {
	.ta-head { gap: 10px; padding-bottom: 10px; }
	.ta-head__actions { width: 100%; }
	.ta-head__buttons > :deep(.p-button) { flex: 1 1 calc(50% - 4px); min-height: 40px; }
	.ta-head__buttons > :deep(.p-button-icon-only) { flex: none; width: 40px; }
	.ta-head__dates { gap: 2px 12px; }
}
</style>

<style>
.ta-head__tooltip { max-width: 320px; }
</style>
