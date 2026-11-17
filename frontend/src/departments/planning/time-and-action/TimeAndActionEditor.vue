<template>
	<section class="ta-editor" :aria-label="`Update ${name}`">
		<Skeleton v-if="loading && !data" height="320px" />
		<Message v-else-if="loadError" severity="error" :closable="false">{{ loadError }}</Message>
		<template v-else-if="data">
			<TimeAndActionHeader :data="data" :total="rows.length" :dated-count="datedCount" :unsaved-count="unsavedCount" :has-errors="counts.error > 0" :busy="busy" @revise="openRevise" @steps="stepsVisible = true" @split="splitVisible = true" @lot-detail="lotDetailVisible = true" @complete="completeVisible = true" @reverted="emit('reverted', $event)" />
			<TimeAndActionStepper :time-and-action="name" :rows="rows" />
			<TimeAndActionTable :time-and-action="name" :rows="rows" :next-index="nextIndex" :chips="chips" :can-edit-suppliers="Boolean(data.can_edit_suppliers)" @actual="setActual" @reason="setReason" @edit-suppliers="editSuppliers" />
			<Message v-if="error" severity="error" :closable="true" role="alert" @close="error = ''">{{ error }}</Message>
			<footer class="ta-editor__savebar">
				<div class="ta-editor__status">
					<span class="ta-editor__counts"><b>{{ counts.done }}</b> done · <b class="is-overdue">{{ counts.overdue }}</b> overdue · <b>{{ counts.due }}</b> due · <b>{{ counts.blocked }}</b> blocked<template v-if="counts.error"> · <b class="is-overdue">{{ counts.error }}</b> to fix</template></span>
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
		<UpdateActionsDialog v-if="data" v-model:visible="stepsVisible" :name="name" :data="data" @saved="stepsSaved" />
		<SplitTimeAndActionDialog v-if="data" v-model:visible="splitVisible" :time-and-action="name" />
		<LotDetailDialog v-if="data" v-model:visible="lotDetailVisible" :against="data.against" :against-id="data.against_id" />
		<PlannedSuppliersDialog v-model:visible="suppliersVisible" :action="suppliersAction" :initial="plannedSupplierValues(chips[suppliersAction])" :on-save="(suppliers) => editor.savePlannedSuppliers(suppliersAction, suppliers)" />
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
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import Textarea from "primevue/textarea"
import { useToast } from "primevue/usetoast"
import { computed, ref, watch } from "vue"

import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import { getDelay, getImpact, getPendingSummary, getReviseMessage, getSaveMessage } from "./timeAndAction.js"
import LotDetailDialog from "./LotDetailDialog.vue"
import PlannedSuppliersDialog from "./PlannedSuppliersDialog.vue"
import SplitTimeAndActionDialog from "./SplitTimeAndActionDialog.vue"
import { plannedSupplierValues } from "./supplierChips.js"
import TimeAndActionHeader from "./TimeAndActionHeader.vue"
import TimeAndActionStepper from "./TimeAndActionStepper.vue"
import TimeAndActionTable from "./TimeAndActionTable.vue"
import UpdateActionsDialog from "./UpdateActionsDialog.vue"
import { useTimeAndActionEditor } from "./useTimeAndActionEditor.js"

/** Cockpit of one T&A: header, stepper, action table and sticky save bar; actual dates are previewed by the server. */
const props = defineProps({ name: { type: String, required: true } })
const emit = defineEmits(["saved", "completed", "dirty", "reverted"])
const toast = useToast()
const editor = useTimeAndActionEditor(props.name)
const { data, rows, nextIndex, counts, datedCount, missingReasons, unsavedCount, hasChanges, canSave, loading, busy, loadError, reset, setActual, setReason, chips } = editor
const error = ref("")
const saving = ref(false)
const saveVisible = ref(false)
const completeVisible = ref(false)
const reviseVisible = ref(false)
const stepsVisible = ref(false)
const splitVisible = ref(false)
const lotDetailVisible = ref(false)
const suppliersVisible = ref(false)
const suppliersAction = ref("")
const reviseReason = ref("")
const reviseError = ref("")

const impact = computed(() => getImpact(data.value, hasChanges.value))
const pending = computed(() => getPendingSummary({ changes: unsavedCount.value, errors: counts.value.error, missingReasons: missingReasons.value }))
const changedRows = computed(() => rows.value.filter((row) => row.edited && !row.error))
const completeMessage = computed(() => {
	const saved = hasChanges.value ? `Your ${unsavedCount.value} unsaved ${unsavedCount.value === 1 ? "change is" : "changes are"} saved first. ` : ""
	return `All ${rows.value.length} actions are dated. ${saved}A completed T&A leaves the open list and can no longer be updated.`
})

function changeSummary(row) {
	if (!row.actual_date) return "Actual date cleared"
	const late = getDelay(row)
	return `Actual ${formatDisplayDate(row.actual_date, "")} · ${late.tone === "late" ? late.text : "on time"}`
}

function editSuppliers(action) {
	suppliersAction.value = action
	suppliersVisible.value = true
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

async function stepsSaved(lines) {
	toast.add({ severity: "success", summary: `Updated ${props.name}: ${lines.join("; ")}.`, life: 4000 })
	await editor.load()
	emit("saved")
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
.ta-editor { display: grid; align-content: start; min-width: 0; gap: 14px; padding: 18px; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-radius-lg); }
.ta-editor__savebar { position: sticky; bottom: 12px; z-index: 10; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px 20px; padding: 10px 14px; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-radius-md); box-shadow: var(--erp-shadow-card); }
.ta-editor__status { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; min-width: 0; }
.ta-editor__counts { color: var(--erp-text-muted); font-size: 13px; }
.ta-editor__counts b { color: var(--erp-text); }
.ta-editor__counts b.is-overdue { color: var(--erp-danger); }
.ta-impact { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 7px; padding: 5px 10px; font-size: 13px; font-weight: 500; border-radius: 7px; }
.ta-impact--late { color: var(--erp-attention-text); background: var(--erp-attention-soft); border: 1px solid var(--erp-attention-border); }
.ta-impact--early { color: var(--erp-success-text); background: var(--erp-success-soft); }
.ta-impact--none { padding-inline: 0; color: var(--erp-text-muted); }
.ta-editor__save { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-left: auto; }
.ta-editor__pending { color: var(--erp-text-muted); font-size: 13px; }
.ta-editor__pending .is-bad { color: var(--erp-danger); font-weight: 600; }
.ta-editor__revise { display: grid; gap: var(--erp-space-2); }
.ta-editor__revise p { margin: 0; }
.ta-change-list { margin: 12px 0 0; padding: 0; list-style: none; border: 1px solid var(--erp-border); border-radius: 7px; }
.ta-change-list li { display: flex; justify-content: space-between; gap: 12px; padding: 8px 12px; font-size: 13px; border-bottom: 1px solid var(--erp-border-subtle); }
.ta-change-list li:last-child { border-bottom: 0; }
@media (max-width: 767px) {
	.ta-editor { padding: 12px; }
	.ta-editor__savebar { position: static; box-shadow: none; }
}
</style>