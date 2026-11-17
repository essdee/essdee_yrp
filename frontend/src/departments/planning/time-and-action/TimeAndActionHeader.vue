<template>
	<header class="ta-head">
		<div class="ta-head__facts">
			<div class="ta-head__title">
				<h2>{{ data.name }}</h2>
				<TimeAndActionChip tone="info" :label="data.status" />
				<span class="ta-head__against">Against {{ againstShortLabel(data.against) }}: <strong>{{ data.against_id }}</strong> · {{ data.item }}</span>
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
				<Button label="Complete T&A" icon="pi pi-check" size="small" :disabled="busy || !data.can_complete || hasErrors" @click="emit('complete')" />
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
const emit = defineEmits(["revise", "steps", "split", "complete"])
const vTooltip = Tooltip
const runningDelay = computed(() => getRunningDelay(props.data.delay))
</script>

<style scoped>
.ta-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 12px 20px; padding-bottom: 14px; border-bottom: 1px solid var(--erp-border); }
.ta-head__facts { display: grid; min-width: 0; gap: 8px; }
.ta-head__title { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
.ta-head__title h2 { margin: 0; font-size: var(--erp-font-size-hero); font-weight: 700; }
.ta-head__against { color: var(--erp-text-muted); font-size: 13px; }
.ta-head__against strong { color: var(--erp-text); }
.ta-head__dates { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 18px; color: var(--erp-text-muted); font-size: 13px; }
.ta-head__dates strong { color: var(--erp-text); font-variant-numeric: tabular-nums; }
.ta-head__running { font-size: 14px; font-weight: 700; }
.ta-head__running--late { color: var(--erp-danger); }
.ta-head__running--ok { color: var(--erp-success-text); }
.ta-head__running--none { color: var(--erp-text-muted); }
.ta-head__actions { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; margin-left: auto; }
.ta-head__buttons { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 8px; }
.ta-head__hint { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
@media (max-width: 767px) {
	.ta-head__actions { align-items: stretch; margin-left: 0; }
	.ta-head__buttons { justify-content: flex-start; }
}
</style>

<style>
.ta-head__tooltip { max-width: 320px; }
</style>
