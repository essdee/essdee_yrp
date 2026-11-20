<template>
	<ol class="ta-steps" aria-label="Action steps">
		<li v-for="row in rows" :key="row.action" class="ta-step" :class="`ta-step--${row.status}`" :title="row.process_name ? undefined : row.blockedBy.length ? `Waiting for ${row.blockedBy.join(', ')}` : row.action">
			<component :is="row.process_name ? ActionQuantities : 'div'" v-bind="row.process_name ? { timeAndAction, action: row.action, process: row.process_name, block: true } : { class: 'ta-step__body' }">
				<span class="ta-step__top">
					<span>STEP {{ row.index + 1 }}</span>
					<span class="ta-step__state"><i v-if="STEP_ICONS[row.status]" :class="STEP_ICONS[row.status]" aria-hidden="true" /><span v-else class="ta-step__dot" aria-hidden="true" />{{ STEP_LABELS[row.status] }}</span>
				</span>
				<span class="ta-step__name">{{ row.action }}</span>
				<span class="ta-step__date">{{ formatDisplayDate(row.actual_date || row.rescheduled_date, "") }}</span>
			</component>
		</li>
	</ol>
</template>

<script setup>
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import ActionQuantities from "./ActionQuantities.vue"
import { STEP_LABELS } from "./timeAndAction.js"

/** Horizontal stepper: one card per action with its state and its actual (else rescheduled) date; process cards open the quantities pop-up. */
defineProps({ rows: { type: Array, required: true }, timeAndAction: { type: String, required: true } })
const STEP_ICONS = { done: "pi pi-check", blocked: "pi pi-lock", error: "pi pi-exclamation-circle" }
</script>

<style scoped>
.ta-steps { display: flex; gap: 8px; min-width: 0; margin: 0; padding: 0 0 4px; overflow-x: auto; list-style: none; scrollbar-width: thin; }
.ta-step { display: grid; flex: 1 0 140px; gap: 3px; min-width: 140px; max-width: 220px; padding: 8px 10px; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-radius-md); }
.ta-step__body { display: grid; gap: 3px; min-width: 0; }
.ta-step__top { display: flex; justify-content: space-between; gap: 6px; color: var(--erp-text-muted); font-size: 10px; font-weight: 700; letter-spacing: .04em; }
.ta-step__state { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
.ta-step__dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.ta-step__state i { font-size: 10px; }
.ta-step__name { overflow: hidden; font-size: var(--erp-font-size-caption); font-weight: 700; white-space: nowrap; text-overflow: ellipsis; }
.ta-step__date { color: var(--erp-text-secondary); font-size: var(--erp-font-size-min); font-variant-numeric: tabular-nums; }
.ta-step--done { background: var(--erp-success-soft); border-color: color-mix(in srgb, var(--erp-success-text) 30%, transparent); }
.ta-step--done .ta-step__state { color: var(--erp-success-text); }
.ta-step--overdue, .ta-step--error { background: var(--erp-danger-soft); border-color: color-mix(in srgb, var(--erp-danger) 40%, transparent); }
.ta-step--overdue .ta-step__state, .ta-step--error .ta-step__state { color: var(--erp-danger); }
.ta-step--due { background: var(--erp-attention-soft); border-color: var(--erp-attention-border); }
.ta-step--due .ta-step__state { color: var(--erp-attention-text); }
.ta-step--blocked { background: var(--erp-surface-muted); opacity: .8; }
.ta-step--blocked .ta-step__name { color: var(--erp-text-muted); }
@media (max-width: 640px) {
	.ta-steps { gap: 6px; scroll-snap-type: x proximity; }
	.ta-step { flex-basis: 128px; min-width: 128px; padding: 6px 8px; scroll-snap-align: start; }
}
</style>
