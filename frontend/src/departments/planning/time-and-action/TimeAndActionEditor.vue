<template>
	<section class="ta-editor" :aria-label="`Update ${name}`">
		<Skeleton v-if="loading && !data" height="320px" />
		<Message v-else-if="loadError" severity="error" :closable="false">{{ loadError }}</Message>
		<template v-else-if="data">
			<header class="ta-editor__strip">
				<div class="ta-editor__progress">
					<span><b>{{ datedCount }}</b> of {{ rows.length }} actions dated</span>
					<span class="ta-editor__bar" aria-hidden="true"><i :style="{ width: `${(datedCount / (rows.length || 1)) * 100}%` }" /></span>
					<span class="ta-editor__legend">
						<TimeAndActionChip tone="done" :label="`${counts.done} done`" />
						<TimeAndActionChip tone="overdue" :label="`${counts.overdue} overdue`" />
						<TimeAndActionChip tone="due" :label="`${counts.due} due`" />
						<TimeAndActionChip tone="blocked" :label="`${counts.blocked} blocked`" />
						<TimeAndActionChip v-if="counts.error" tone="error" :label="`${counts.error} to fix`" />
					</span>
				</div>
				<div class="ta-editor__actions">
					<div class="ta-editor__buttons">
						<Button v-tooltip.left="{ value: REVISE_HELP, class: 'ta-editor__tooltip' }" icon="pi pi-info-circle" text rounded severity="secondary" size="small" aria-label="What Revise Dates does" />
						<Button label="Revise Dates" icon="pi pi-refresh" severity="secondary" outlined size="small" :disabled="busy || !data.can_revise" :title="data.can_revise ? 'Make the current Rescheduled Dates the new Freeze Dates' : 'Only the revised-date approver can revise, a limited number of times'" @click="openRevise" />
						<Button label="Complete T&A" icon="pi pi-check" size="small" :disabled="busy || !data.can_complete || counts.error > 0" @click="completeVisible = true" />
					</div>
					<span class="ta-editor__hint">{{ data.can_complete ? `All ${rows.length} actions are dated` : `Complete unlocks when every action is dated · ${rows.length - datedCount} left` }}</span>
				</div>
			</header>
			<div class="ta-editor__scroll">
				<table class="erp-data-table ta-acts">
					<colgroup><col class="ta-col-status"><col class="ta-col-action"><col class="ta-col-station"><col class="ta-col-planned"><col class="ta-col-rescheduled"><col class="ta-col-actual"><col class="ta-col-reason"><col class="ta-col-delay"></colgroup>
					<thead><tr><th>Status</th><th>Action</th><th>Work Station</th><th>Planned Date</th><th>Rescheduled Date</th><th>Actual Date</th><th>Reason</th><th>Delay</th></tr></thead>
					<tbody>
						<template v-for="row in rows" :key="row.action">
							<tr :class="rowClass(row)">
								<td>
									<TimeAndActionChip :tone="row.status" :label="STATUS_LABELS[row.status]" />
									<small v-if="statusNote(row)" class="ta-acts__sub">{{ statusNote(row) }}</small>
								</td>
								<td>
									<div class="ta-acts__name" :title="row.action">{{ row.action }}</div>
									<div class="ta-acts__meta" :title="metaLine(row)"><span class="ta-acts__idx">#{{ row.index + 1 }}</span>&nbsp;· {{ row.department }} · {{ dayCount(row.lead_time) }} lead</div>
									<div v-if="row.status === 'blocked'" class="ta-acts__waiting" :title="`Waiting for ${row.blockedBy.join(', ')}`"><i class="pi pi-lock" aria-hidden="true" /> Waiting for {{ row.blockedBy.join(", ") }}</div>
								</td>
								<td><span v-if="row.work_station">{{ row.work_station }}</span><span v-else class="ta-subtle">—</span></td>
								<td class="ta-acts__planned">{{ formatDisplayDate(row.planned_start_date, "") }}</td>
								<td class="ta-acts__rescheduled" :class="{ 'is-shifted': row.rescheduled_date !== row.planned_start_date }">
									<span v-if="row.oldRescheduledDate" class="ta-acts__moved"><s>{{ formatDisplayDate(row.oldRescheduledDate, "") }}</s><b :class="{ 'is-earlier': row.rescheduled_date < row.oldRescheduledDate }">{{ formatDisplayDate(row.rescheduled_date, "") }}</b></span>
									<template v-else>{{ formatDisplayDate(row.rescheduled_date, "") }}</template>
								</td>
								<td class="ta-acts__actual"><DateField :model-value="row.inputValue" :aria-label="`Actual Date of ${row.action}`" :disabled="!row.editable" :invalid="Boolean(row.error)" :show-on-focus="false" @update:model-value="(value) => setActual(row, value)" /></td>
								<td>
									<InputText v-if="row.late && row.editable" :model-value="row.reason || ''" size="small" fluid :invalid="row.needsReason" placeholder="Why late? Required" :aria-label="`Reason for ${row.action}`" @update:model-value="(value) => setReason(row, value)" />
									<span v-else-if="row.reason">{{ row.reason }}</span>
									<span v-else class="ta-subtle">{{ row.actual_date && !row.error ? "Not needed" : "—" }}</span>
								</td>
								<td>
									<template v-if="delay(row)"><span class="ta-acts__delay" :class="`ta-acts__delay--${delay(row).tone}`">{{ delay(row).text }}</span><small class="ta-acts__sub">Planned Delay {{ delay(row).planned }}</small></template>
									<span v-else class="ta-subtle">—</span>
								</td>
							</tr>
							<tr v-if="row.error" class="ta-acts__error"><td colspan="8"><div role="alert"><i class="pi pi-exclamation-circle" aria-hidden="true" />{{ row.error }}</div></td></tr>
						</template>
					</tbody>
				</table>
			</div>
			<Message v-if="error" severity="error" :closable="true" role="alert" @close="error = ''">{{ error }}</Message>
			<footer class="ta-editor__savebar">
				<div class="ta-editor__delivery">
					<div><div class="ta-label">Expected Delivery · {{ name }}</div><div class="ta-editor__big">{{ formatDisplayDate(data.end_date, "") }}</div></div>
					<span class="ta-impact" :class="`ta-impact--${impact.tone}`">
						<template v-if="impact.from"><i :class="impact.tone === 'late' ? 'pi pi-exclamation-circle' : 'pi pi-check'" aria-hidden="true" />Expected delivery moves {{ impact.from }} <i class="pi pi-arrow-right" aria-hidden="true" /> {{ impact.to }}, {{ impact.text }}</template>
						<template v-else>{{ impact.text }}</template>
					</span>
				</div>
				<div class="ta-editor__save">
					<span class="ta-editor__pending"><template v-for="(part, index) in pending" :key="part"><template v-if="index"> · </template><span :class="{ 'is-bad': index > 0 }">{{ part }}</span></template></span>
					<Button label="Discard" text severity="secondary" :disabled="!unsavedCount || busy" @click="reset" />
					<Button label="Save" :disabled="!canSave" :loading="saving" @click="requestSave" />
				</div>
			</footer>
		</template>
		<DocumentConfirmationDialog v-model:visible="saveVisible" :title="`Save ${name}?`" :message="getSaveMessage(data)" confirm-label="Save" cancel-label="Keep editing" severity="primary" icon="pi pi-calendar" :busy="saving" @confirm="commit">
			<ul class="ta-change-list"><li v-for="row in changedRows" :key="row.action"><b>{{ row.action }}</b><span>{{ changeSummary(row) }}</span></li></ul>
		</DocumentConfirmationDialog>
		<DocumentConfirmationDialog v-model:visible="completeVisible" :title="`Complete ${name}?`" :message="completeMessage" confirm-label="Complete T&A" cancel-label="Cancel" severity="primary" icon="pi pi-check-circle" :busy="saving" @confirm="runComplete" />
		<Dialog v-model:visible="reviseVisible" modal :header="`Revise Dates of ${name}`" class="erp-dialog--sm">
			<div class="ta-editor__revise">
				<p>{{ getReviseMessage(data) }}</p>
				<Message v-if="unsavedCount" severity="warn" :closable="false">Save or discard your unsaved changes before revising.</Message>
				<label class="erp-field-label" for="ta-revise-reason">Reason<span class="erp-required-mark" aria-hidden="true">*</span></label>
				<Textarea id="ta-revise-reason" v-model="reviseReason" rows="3" fluid placeholder="For example: Buyer moved the fabric approval" />
				<Message v-if="reviseError" severity="error" :closable="false">{{ reviseError }}</Message>
			</div>
			<template #footer>
				<Button label="Cancel" severity="secondary" text :disabled="saving" @click="reviseVisible = false" />
				<Button label="Revise Dates" icon="pi pi-refresh" :loading="saving" :disabled="!reviseReason.trim() || unsavedCount > 0" @click="runRevise" />
			</template>
		</Dialog>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import Textarea from "primevue/textarea"
import Tooltip from "primevue/tooltip"
import { useToast } from "primevue/usetoast"
import { computed, ref, watch } from "vue"

import DateField from "../../../components/common/DateField.vue"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import TimeAndActionChip from "./TimeAndActionChip.vue"
import { REVISE_HELP, STATUS_LABELS, dayCount, getDelay, getImpact, getPendingSummary, getReviseMessage, getSaveMessage, getStatusNote } from "./timeAndAction.js"
import { useTimeAndActionEditor } from "./useTimeAndActionEditor.js"

/** Inline editor of one open T&A: actual dates previewed by the server, sticky save bar, Revise Dates and Complete T&A. */
const props = defineProps({ name: { type: String, required: true } })
const emit = defineEmits(["saved", "completed", "dirty"])
const vTooltip = Tooltip
const toast = useToast()
const editor = useTimeAndActionEditor(props.name)
const { data, rows, nextIndex, counts, datedCount, missingReasons, unsavedCount, hasChanges, canSave, loading, busy, loadError, today, reset, setActual, setReason } = editor
const error = ref("")
const saving = ref(false)
const saveVisible = ref(false)
const completeVisible = ref(false)
const reviseVisible = ref(false)
const reviseReason = ref("")
const reviseError = ref("")

const impact = computed(() => getImpact(data.value, hasChanges.value))
const pending = computed(() => getPendingSummary({ changes: unsavedCount.value, errors: counts.value.error, missingReasons: missingReasons.value }))
const changedRows = computed(() => rows.value.filter((row) => row.edited && !row.error))
const completeMessage = computed(() => {
	const saved = hasChanges.value ? `Your ${unsavedCount.value} unsaved ${unsavedCount.value === 1 ? "change is" : "changes are"} saved first. ` : ""
	return `All ${rows.value.length} actions are dated. ${saved}A completed T&A leaves the open list and can no longer be updated.`
})

function rowClass(row) {
	return {
		[`is-${row.status}`]: true,
		"is-next": row.index === nextIndex.value && row.status !== "overdue",
		"is-edited": row.edited && !row.error,
		"has-error": Boolean(row.error),
	}
}

const metaLine = (row) => `#${row.index + 1} · ${row.department} · ${dayCount(row.lead_time)} lead`
const statusNote = (row) => getStatusNote(row, row.status, { today, isNext: row.index === nextIndex.value })
const delay = (row) => (row.error ? null : getDelay(row))

function changeSummary(row) {
	if (!row.actual_date) return "Actual date cleared"
	const late = getDelay(row)
	return `Actual ${formatDisplayDate(row.actual_date, "")} · ${late.tone === "late" ? late.text : "on time"}`
}

function requestSave() {
	if (Number(data.value.delivery_days_moved) > 0) saveVisible.value = true
	else commit()
}

async function run(action, success) {
	saving.value = true
	error.value = ""
	try {
		await action()
		if (success) toast.add({ severity: "success", summary: success(), life: 3000 })
		return true
	} catch (reason) {
		error.value = reason?.message || "Unable to update this Time and Action."
		return false
	} finally {
		saving.value = false
		saveVisible.value = false
		completeVisible.value = false
	}
}

async function commit() {
	const expected = formatDisplayDate(data.value.end_date, "")
	if (await run(editor.save, () => `Saved ${props.name}. Expected delivery ${expected}.`)) emit("saved")
}

async function runComplete() {
	if (await run(editor.complete, () => `${props.name} completed.`)) emit("completed", props.name)
}

function openRevise() {
	reviseReason.value = ""
	reviseError.value = ""
	reviseVisible.value = true
}

async function runRevise() {
	saving.value = true
	reviseError.value = ""
	try {
		await editor.revise(reviseReason.value.trim())
		reviseVisible.value = false
		toast.add({ severity: "success", summary: "Dates revised. Freeze Dates now match the Rescheduled Dates.", life: 3000 })
		emit("saved")
	} catch (reason) {
		reviseError.value = reason?.message || "Unable to revise the dates."
	} finally {
		saving.value = false
	}
}

watch(unsavedCount, (count) => emit("dirty", count), { immediate: true })
editor.load()
</script>

<style scoped>
.ta-editor { display: grid; min-width: 0; margin: 8px 16px 16px 40px; background: var(--erp-surface); border: 1px solid var(--erp-border); border-left: 3px solid var(--erp-accent); border-radius: var(--erp-radius-md); box-shadow: var(--erp-shadow-card); }
.ta-editor > .p-skeleton, .ta-editor > .p-message { margin: 12px; }
.ta-editor__strip { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px 20px; padding: 12px 16px; background: var(--erp-surface-soft); border-bottom: 1px solid var(--erp-border); border-radius: var(--erp-radius-md) var(--erp-radius-md) 0 0; }
.ta-editor__progress { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; font-size: 13px; }
.ta-editor__bar { position: relative; width: 180px; height: 6px; overflow: hidden; background: var(--erp-surface-muted); border-radius: 99px; }
.ta-editor__bar i { position: absolute; inset: 0 auto 0 0; background: var(--erp-success); border-radius: 99px; }
.ta-editor__legend { display: flex; flex-wrap: wrap; gap: 6px; }
.ta-editor__actions { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; margin-left: auto; }
.ta-editor__buttons { display: flex; align-items: center; gap: 8px; }
.ta-editor__hint { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.ta-editor__scroll { min-width: 0; max-height: min(70vh, 760px); overflow: auto; }
.ta-acts { table-layout: fixed; min-width: 1060px; }
.ta-col-status { width: 108px; } .ta-col-station { width: 128px; } .ta-col-planned { width: 104px; } .ta-col-rescheduled { width: 116px; }
.ta-col-actual { width: 176px; } .ta-col-reason { width: 22%; } .ta-col-delay { width: 118px; }
.ta-editor .ta-acts.erp-data-table > thead > tr > th { position: sticky; top: 0; z-index: 2; padding: 10px 12px; white-space: normal; line-height: 1.25; background: var(--erp-report-head-bg); border-bottom: 1px solid var(--erp-border-strong); color: var(--erp-text-secondary); }
.ta-editor .ta-acts.erp-data-table > tbody > tr > td { height: 56px; padding: 7px 12px; vertical-align: middle; background: var(--ta-row-bg, transparent); border-bottom: 1px solid var(--erp-border); box-shadow: var(--ta-hover, 0 0 #0000); }
.ta-editor .ta-acts.erp-data-table > tbody > tr > td:first-child { box-shadow: var(--ta-row-mark, 0 0 #0000), var(--ta-hover, 0 0 #0000); }
.ta-editor .ta-acts.erp-data-table > tbody > tr:nth-child(even) { --ta-row-bg: color-mix(in srgb, var(--erp-surface-muted) 45%, transparent); }
.ta-editor .ta-acts.erp-data-table > tbody > tr:hover { --ta-hover: inset 0 0 0 999px color-mix(in srgb, var(--erp-text) 4%, transparent); }
.ta-editor .ta-acts.erp-data-table > tbody > tr.is-done { --ta-row-bg: color-mix(in srgb, var(--erp-success-soft) 55%, transparent); --ta-row-mark: inset 3px 0 0 var(--erp-success); }
.ta-editor .ta-acts.erp-data-table > tbody > tr.is-overdue { --ta-row-bg: color-mix(in srgb, var(--erp-danger-soft) 55%, transparent); --ta-row-mark: inset 3px 0 0 var(--erp-danger); }
.ta-editor .ta-acts.erp-data-table > tbody > tr.is-due { --ta-row-mark: inset 3px 0 0 var(--erp-attention); }
.ta-editor .ta-acts.erp-data-table > tbody > tr.is-next { --ta-row-bg: color-mix(in srgb, var(--erp-attention-soft) 60%, transparent); }
.ta-editor .ta-acts.erp-data-table > tbody > tr.is-blocked { --ta-row-bg: transparent; }
.ta-editor .ta-acts.erp-data-table > tbody > tr.is-edited { --ta-row-bg: var(--erp-accent-soft); --ta-row-mark: inset 3px 0 0 var(--erp-accent); }
.ta-editor .ta-acts.erp-data-table > tbody > tr.has-error, .ta-editor .ta-acts.erp-data-table > tbody > tr.ta-acts__error { --ta-row-bg: var(--erp-danger-soft); --ta-row-mark: inset 3px 0 0 var(--erp-danger); }
.ta-editor .ta-acts.erp-data-table > tbody > tr.has-error > td { border-bottom: 0; }
.ta-editor .ta-acts.erp-data-table > tbody > tr.is-blocked > td { color: var(--erp-text-subtle); }
.ta-acts tr.is-blocked .ta-acts__name { color: var(--erp-text-muted); font-weight: 500; }
.ta-acts__name { display: -webkit-box; overflow: hidden; -webkit-line-clamp: 2; -webkit-box-orient: vertical; font-weight: 600; line-height: 1.3; color: var(--erp-text); }
.ta-acts__meta, .ta-acts__waiting { overflow: hidden; margin-top: 2px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); white-space: nowrap; text-overflow: ellipsis; }
.ta-acts__idx { color: var(--erp-text-subtle); }
.ta-acts__waiting i { font-size: 10px; }
.ta-acts__sub { display: block; margin-top: 2px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 400; white-space: nowrap; }
.ta-acts td.ta-acts__planned, .ta-acts td.ta-acts__rescheduled { color: var(--erp-text-muted); white-space: nowrap; }
.ta-acts td.ta-acts__rescheduled.is-shifted { color: var(--erp-attention-text); font-weight: 600; }
.ta-acts tr.is-done td.ta-acts__rescheduled.is-shifted, .ta-acts tr.is-blocked td.ta-acts__rescheduled.is-shifted { color: var(--erp-text-secondary); font-weight: 500; }
.ta-acts__moved s { display: block; color: var(--erp-text-subtle); font-size: var(--erp-font-size-caption); font-weight: 400; }
.ta-acts__moved b { color: var(--erp-attention-text); font-weight: 600; }
.ta-acts__moved b.is-earlier { color: var(--erp-success-text); }
.ta-acts__actual :deep(.p-datepicker-input) { height: 34px; padding-inline: 8px; font-weight: 600; font-size: 13px; color: var(--erp-text); background: var(--erp-surface); border-color: var(--erp-border-strong); }
.ta-acts__actual :deep(.p-datepicker-dropdown) { height: 34px; }
.ta-acts tr:not(.is-blocked) .ta-acts__actual :deep(.p-datepicker-input:enabled) { box-shadow: 0 1px 2px rgb(0 0 0 / 6%); }
.ta-acts__actual :deep(.p-datepicker-input::placeholder) { font-weight: 400; }
.ta-acts__actual :deep(.p-datepicker-input:disabled) { color: var(--erp-text-subtle); background: var(--erp-surface-muted); border-color: var(--erp-border); }
.ta-acts :deep(.p-inputtext.p-inputtext-sm) { height: 32px; }
.ta-acts__delay { font-weight: 600; }
.ta-acts__delay--late { color: var(--erp-danger); }
.ta-acts__delay--ok { color: var(--erp-success-text); }
.ta-editor .ta-acts.erp-data-table > tbody > tr.ta-acts__error > td { height: auto; padding: 0 12px 10px; }
.ta-acts__error div { display: flex; align-items: center; gap: 7px; color: var(--erp-danger); font-size: 13px; font-weight: 500; }
.ta-subtle { color: var(--erp-text-subtle); }
.ta-label { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
.ta-editor__savebar { position: sticky; bottom: 12px; z-index: 10; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px 20px; margin: 12px 0 0; padding: 12px 18px; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-radius-md); box-shadow: var(--erp-shadow-card); }
.ta-editor__delivery { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; }
.ta-editor__big { font-size: var(--erp-font-size-section); font-weight: 700; font-variant-numeric: tabular-nums; }
.ta-impact { display: inline-flex; align-items: center; gap: 7px; padding: 5px 10px; font-size: 13px; font-weight: 500; border-radius: 7px; }
.ta-impact--late { color: var(--erp-attention-text); background: var(--erp-attention-soft); border: 1px solid var(--erp-attention-border); }
.ta-impact--early { color: var(--erp-success-text); background: var(--erp-success-soft); }
.ta-impact--none { color: var(--erp-text-muted); }
.ta-editor__save { display: flex; align-items: center; gap: 10px; }
.ta-editor__pending { color: var(--erp-text-muted); font-size: 13px; }
.ta-editor__pending .is-bad { color: var(--erp-danger); font-weight: 600; }
.ta-editor > .p-message { margin: 12px 16px 0; }
.ta-editor__revise { display: grid; gap: var(--erp-space-2); }
.ta-editor__revise p { margin: 0; }
.ta-change-list { margin: 12px 0 0; padding: 0; list-style: none; border: 1px solid var(--erp-border); border-radius: 7px; }
.ta-change-list li { display: flex; justify-content: space-between; gap: 12px; padding: 8px 12px; font-size: 13px; border-bottom: 1px solid var(--erp-border-subtle); }
.ta-change-list li:last-child { border-bottom: 0; }
</style>

<style>
.ta-editor__tooltip { max-width: 320px; }
</style>
