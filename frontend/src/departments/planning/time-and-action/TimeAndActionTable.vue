<template>
	<div class="ta-table" role="region" tabindex="0" aria-label="Actions">
		<table class="erp-data-table ta-acts">
			<colgroup><col class="ta-col-action"><col class="ta-col-planned"><col class="ta-col-rescheduled"><col class="ta-col-actual"><col class="ta-col-reason"><col class="ta-col-delay"></colgroup>
			<thead><tr><th>Action</th><th>Planned / Freeze</th><th>Rescheduled</th><th>Actual Date</th><th>Reason</th><th class="ta-acts__right">Delay</th></tr></thead>
			<tbody>
				<template v-for="row in rows" :key="row.action">
					<tr :class="rowClass(row)">
						<td class="ta-acts__main">
							<div class="ta-acts__name" :title="row.process_name ? undefined : row.action"><span class="ta-acts__idx">#{{ row.index + 1 }}</span> <ActionQuantities v-if="row.process_name" :time-and-action="timeAndAction" :action="row.action" :process="row.process_name">{{ row.action }}</ActionQuantities><template v-else>{{ row.action }}</template><span class="ta-sr"> ({{ STATUS_LABELS[row.status] }})</span></div>
							<span class="ta-acts__status" :class="`ta-acts__status--${row.status}`" aria-hidden="true">{{ STATUS_LABELS[row.status] }}</span>
							<div class="ta-acts__sub">
								<span class="ta-acts__meta">{{ row.department }} · {{ row.lead_time }}d lead<template v-if="row.work_station"> · <i class="pi pi-wrench" aria-hidden="true" /> {{ row.work_station }}</template></span>
								<SupplierChips v-if="chips[row.action]?.length || canEditSuppliers" :chips="chips[row.action]" :action="row.action" :editable="canEditSuppliers" @edit="emit('edit-suppliers', row.action)" />
							</div>
							<div v-if="row.status === 'blocked'" class="ta-acts__waiting" :title="`Waiting for ${row.blockedBy.join(', ')}`"><i class="pi pi-lock" aria-hidden="true" /> Waiting for {{ row.blockedBy.join(", ") }}</div>
						</td>
						<td class="ta-acts__planned" data-label="Planned / Freeze">
							<div>P: {{ formatDisplayDate(row.planned_start_date, "") }}</div>
							<div class="ta-acts__freeze">F: {{ formatDisplayDate(row.date, "") }}</div>
						</td>
						<td class="ta-acts__rescheduled" data-label="Rescheduled" :class="{ 'is-shifted': row.rescheduled_date !== row.date }">
							<span v-if="row.oldRescheduledDate" class="ta-acts__moved"><s>{{ formatDisplayDate(row.oldRescheduledDate, "") }}</s><b :class="{ 'is-earlier': row.rescheduled_date < row.oldRescheduledDate }">{{ formatDisplayDate(row.rescheduled_date, "") }}</b></span>
							<template v-else>{{ formatDisplayDate(row.rescheduled_date, "") }}</template>
						</td>
						<td class="ta-acts__actual" data-label="Actual Date">
							<DateField :model-value="row.inputValue" :aria-label="`Actual Date of ${row.action}`" :disabled="!row.editable" :invalid="Boolean(row.error)" :show-on-focus="false" @update:model-value="(value) => emit('actual', row, value)" />
							<span v-if="row.auto_actual_date && !row.edited" class="ta-acts__auto" title="Set automatically from the linked documents">auto</span>
						</td>
						<td class="ta-acts__reason" data-label="Reason">
							<InputText v-if="row.editable" :model-value="row.reason || ''" size="small" fluid :invalid="row.needsReason" :placeholder="row.late ? 'Why late? Required' : 'Remarks (optional)'" :aria-label="`Reason for ${row.action}`" @update:model-value="(value) => emit('reason', row, value)" />
							<span v-else-if="row.reason">{{ row.reason }}</span>
							<span v-else class="ta-subtle">—</span>
						</td>
						<td class="ta-acts__right ta-acts__delaycell" data-label="Delay">
							<span v-if="delay(row)" class="ta-acts__delay" :class="`ta-acts__delay--${delay(row).tone}`">{{ delay(row).text }}</span>
							<span v-else class="ta-subtle">—</span>
						</td>
					</tr>
					<tr v-if="row.error" class="ta-acts__error"><td colspan="6"><div role="alert"><i class="pi pi-exclamation-circle" aria-hidden="true" />{{ row.error }}</div></td></tr>
				</template>
			</tbody>
		</table>
	</div>
</template>

<script setup>
import InputText from "primevue/inputtext"

import DateField from "../../../components/common/DateField.vue"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import ActionQuantities from "./ActionQuantities.vue"
import SupplierChips from "./SupplierChips.vue"
import { STATUS_LABELS, getDelay } from "./timeAndAction.js"

/** Action table of the cockpit: one row per action with its dates, actual date and reason inputs, and delay. */
const props = defineProps({
	timeAndAction: { type: String, required: true },
	rows: { type: Array, required: true },
	nextIndex: { type: Number, default: -1 },
	chips: { type: Object, default: () => ({}) },
	canEditSuppliers: { type: Boolean, default: false },
})
const emit = defineEmits(["actual", "reason", "edit-suppliers"])

function rowClass(row) {
	return {
		[`is-${row.status}`]: true,
		"is-late": row.status === "done" && Number(row.date_diff) < 0,
		"is-next": row.index === props.nextIndex && row.status !== "overdue",
		"is-edited": row.edited && !row.error,
		"has-error": Boolean(row.error),
	}
}

const delay = (row) => (row.error ? null : getDelay(row))
</script>

<style scoped>
.ta-table { min-width: 0; max-height: max(320px, calc(100vh - 500px)); overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-radius-md); }
.ta-acts { table-layout: fixed; min-width: 860px; }
.ta-col-action { width: 34%; } .ta-col-planned { width: 128px; } .ta-col-rescheduled { width: 112px; }
.ta-col-actual { width: 178px; } .ta-col-reason { width: 18%; } .ta-col-delay { width: 112px; }
.ta-table .ta-acts.erp-data-table > thead > tr > th { position: sticky; top: 0; z-index: 2; padding: 9px 12px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-min); letter-spacing: .05em; text-transform: uppercase; white-space: nowrap; background: var(--erp-report-head-bg); border-bottom: 1px solid var(--erp-border-strong); }
.ta-table .ta-acts.erp-data-table > tbody > tr > td { padding: 9px 12px; vertical-align: middle; background: var(--ta-row-bg, transparent); border-bottom: 1px solid var(--erp-border); box-shadow: var(--ta-hover, 0 0 #0000); }
.ta-table .ta-acts.erp-data-table > tbody > tr > td:first-child { box-shadow: var(--ta-row-mark, 0 0 #0000), var(--ta-hover, 0 0 #0000); }
.ta-table .ta-acts.erp-data-table > tbody > tr:hover { --ta-hover: inset 0 0 0 999px color-mix(in srgb, var(--erp-text) 4%, transparent); }
.ta-table .ta-acts.erp-data-table > tbody > tr.is-done { --ta-row-bg: color-mix(in srgb, var(--erp-success-soft) 70%, transparent); }
.ta-table .ta-acts.erp-data-table > tbody > tr.is-overdue, .ta-table .ta-acts.erp-data-table > tbody > tr.is-late { --ta-row-bg: color-mix(in srgb, var(--erp-danger-soft) 70%, transparent); }
.ta-table .ta-acts.erp-data-table > tbody > tr.is-due { --ta-row-mark: inset 3px 0 0 var(--erp-attention); }
.ta-table .ta-acts.erp-data-table > tbody > tr.is-next { --ta-row-bg: color-mix(in srgb, var(--erp-attention-soft) 35%, transparent); }
.ta-table .ta-acts.erp-data-table > tbody > tr.is-edited { --ta-row-mark: inset 3px 0 0 var(--erp-accent); }
.ta-table .ta-acts.erp-data-table > tbody > tr.has-error, .ta-table .ta-acts.erp-data-table > tbody > tr.ta-acts__error { --ta-row-bg: var(--erp-danger-soft); --ta-row-mark: inset 3px 0 0 var(--erp-danger); }
.ta-table .ta-acts.erp-data-table > tbody > tr.has-error > td { border-bottom: 0; }
.ta-table .ta-acts.erp-data-table > tbody > tr.is-blocked > td { color: var(--erp-text-subtle); }
.ta-acts tr.is-blocked .ta-acts__name { color: var(--erp-text-muted); font-weight: 500; }
.ta-acts__name { display: -webkit-box; overflow: hidden; -webkit-line-clamp: 2; -webkit-box-orient: vertical; font-weight: 700; line-height: 1.3; color: var(--erp-text); }
.ta-acts__idx { color: var(--erp-text-muted); }
.ta-acts__meta, .ta-acts__waiting { overflow: hidden; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); white-space: nowrap; text-overflow: ellipsis; }
.ta-acts__meta i, .ta-acts__waiting i { font-size: 10px; }
.ta-acts__waiting { color: var(--erp-attention-text); font-weight: 500; }
.ta-acts__sub { display: flex; flex-wrap: wrap; align-items: center; gap: 2px 8px; margin-top: 2px; }
.ta-acts__sub :deep(.p-button) { width: 26px; height: 26px; }
.ta-acts td.ta-acts__planned { color: var(--erp-text-secondary); white-space: nowrap; font-variant-numeric: tabular-nums; }
.ta-acts__freeze { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.ta-acts td.ta-acts__rescheduled { color: var(--erp-text); font-weight: 700; white-space: nowrap; font-variant-numeric: tabular-nums; }
.ta-acts td.ta-acts__rescheduled.is-shifted { color: var(--erp-attention-text); }
.ta-acts tr.is-done td.ta-acts__rescheduled.is-shifted, .ta-acts tr.is-blocked td.ta-acts__rescheduled.is-shifted { color: var(--erp-text-secondary); }
.ta-acts__moved s { display: block; color: var(--erp-text-subtle); font-size: var(--erp-font-size-caption); font-weight: 400; }
.ta-acts__moved b { color: var(--erp-attention-text); }
.ta-acts__moved b.is-earlier { color: var(--erp-success-text); }
.ta-acts__actual { position: relative; }
.ta-acts__actual :deep(.p-datepicker-input) { height: 34px; padding-inline: 8px; font-weight: 600; font-size: 13px; color: var(--erp-text); background: var(--erp-surface); border-color: var(--erp-border-strong); }
.ta-acts__actual :deep(.p-datepicker-dropdown) { height: 34px; }
.ta-acts__actual :deep(.p-datepicker-input::placeholder) { font-weight: 400; }
.ta-acts__actual :deep(.p-datepicker-input:disabled) { color: var(--erp-text-subtle); background: var(--erp-surface-muted); border-color: var(--erp-border); }
.ta-acts__auto { display: inline-block; margin-top: 3px; padding: 0 6px; color: var(--erp-info); font-size: var(--erp-font-size-min); font-weight: 700; letter-spacing: .04em; text-transform: uppercase; background: var(--erp-info-soft); border-radius: 4px; }
.ta-acts :deep(.p-inputtext.p-inputtext-sm) { height: 32px; }
.ta-acts__right { text-align: right; }
.ta-acts__delay { font-size: 13px; font-weight: 700; white-space: nowrap; }
.ta-acts__delay--late { color: var(--erp-danger); }
.ta-acts__delay--ok { color: var(--erp-success-text); }
.ta-table .ta-acts.erp-data-table > tbody > tr.ta-acts__error > td { padding: 0 12px 10px; }
.ta-acts__error div { display: flex; align-items: center; gap: 7px; color: var(--erp-danger); font-size: 13px; font-weight: 500; }
.ta-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.ta-subtle { color: var(--erp-text-subtle); }
.ta-acts__status { display: none; }
@media (max-width: 640px) {
	.ta-table { max-height: none; overflow: visible; border: 0; border-radius: 0; }
	.ta-acts, .ta-acts > tbody { display: block; min-width: 0; }
	.ta-acts > colgroup, .ta-acts > thead { display: none; }
	.ta-table .ta-acts.erp-data-table > tbody > tr { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); grid-template-areas: "main main" "planned rescheduled" "actual delay" "reason reason"; gap: 8px 12px; margin-bottom: 8px; padding: 10px 12px; background: var(--ta-row-bg, var(--erp-surface)); border: 1px solid var(--erp-border); border-radius: var(--erp-radius-md); box-shadow: var(--ta-row-mark, 0 0 #0000); }
	.ta-table .ta-acts.erp-data-table > tbody > tr > td, .ta-table .ta-acts.erp-data-table > tbody > tr > td:first-child { display: block; min-width: 0; padding: 0; background: none; border: 0; box-shadow: none; }
	.ta-table .ta-acts.erp-data-table > tbody > tr.has-error { margin-bottom: 0; border-bottom: 0; border-radius: var(--erp-radius-md) var(--erp-radius-md) 0 0; }
	.ta-table .ta-acts.erp-data-table > tbody > tr.ta-acts__error { display: block; margin: 0 0 8px; padding: 0 12px 10px; border-top: 0; border-radius: 0 0 var(--erp-radius-md) var(--erp-radius-md); }
	.ta-table .ta-acts.erp-data-table > tbody > tr.ta-acts__error > td { padding: 0; }
	.ta-acts td[data-label]::before { content: attr(data-label); display: block; margin-bottom: 2px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
	.ta-table .ta-acts.erp-data-table > tbody > tr > td.ta-acts__main { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 4px 8px; grid-area: main; }
	.ta-acts__name { flex: 1 1 0; min-width: 0; font-size: 15px; }
	.ta-acts__sub, .ta-acts__waiting { flex-basis: 100%; }
	.ta-acts__waiting { white-space: normal; }
	.ta-acts__status { display: inline-block; flex: none; padding: 2px 8px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-min); font-weight: 700; white-space: nowrap; background: var(--erp-surface-muted); border-radius: 999px; }
	.ta-acts__status--done { color: var(--erp-success-text); background: var(--erp-success-soft); }
	.ta-acts__status--overdue, .ta-acts__status--error { color: var(--erp-danger); background: var(--erp-danger-soft); }
	.ta-acts__status--due { color: var(--erp-attention-text); background: var(--erp-attention-soft); }
	.ta-acts td.ta-acts__planned { grid-area: planned; }
	.ta-acts td.ta-acts__rescheduled { grid-area: rescheduled; }
	.ta-acts td.ta-acts__actual { grid-area: actual; }
	.ta-acts td.ta-acts__delaycell { grid-area: delay; align-self: start; text-align: left; }
	.ta-acts td.ta-acts__reason { grid-area: reason; }
	.ta-acts__sub :deep(.p-button) { width: 40px; height: 40px; }
	.ta-acts__actual :deep(.p-datepicker-input) { height: 40px; font-size: 16px; }
	.ta-acts__actual :deep(.p-datepicker-dropdown) { width: 40px; height: 40px; }
	.ta-acts :deep(.p-inputtext.p-inputtext-sm) { height: 40px; font-size: 16px; }
}
</style>
