<template>
	<section class="ta-editor" :aria-label="`Time and Action ${name}`">
		<Skeleton v-if="loading && !data" height="320px" />
		<Message v-else-if="loadError" severity="error" :closable="false">{{ loadError }}</Message>
		<template v-else-if="data">
			<header class="ta-editor__bar">
				<div class="ta-editor__summary">
					<span><b>T&A</b> <DocumentLink doctype="SD YRP Time and Action" :name="data.name" /></span>
					<span><b>{{ data.against === "SD YRP Lot" ? "Lot" : "Production Order" }}</b> <DocumentLink :doctype="data.against" :name="data.against_id" /></span>
					<span><b>Master</b> {{ data.master }}</span>
					<span><b>Item</b> {{ data.item }}</span>
					<span><b>Qty</b> {{ data.qty }}</span>
					<span><b>Start</b> {{ formatDisplayDate(data.start_date, "") }}</span>
					<span :class="{ 'ta-editor__late': data.end_date_delay }"><b>Expected End</b> {{ formatDisplayDate(data.end_date, "") }}</span>
					<span><b>Delay</b> {{ data.delay }} / {{ data.rescheduled_delay }}</span>
					<span><b>Performance</b> {{ data.performance }}%</span>
					<span><b>Status</b> {{ data.status }}</span>
				</div>
				<div class="ta-editor__actions">
					<Button v-if="data.can_complete && !isEdited" label="Complete T&A" icon="pi pi-check-circle" severity="success" size="small" :disabled="busy" @click="completeVisible = true" />
					<Button v-if="data.can_revise && !isEdited" label="Revise Dates" icon="pi pi-calendar" severity="secondary" outlined size="small" :disabled="busy" @click="reviseVisible = true" />
					<template v-if="isEdited">
						<Tag value="Not Saved" severity="warn" />
						<Button label="Discard" severity="secondary" text size="small" :disabled="busy" @click="load" />
						<Button label="Save T&A" icon="pi pi-check" size="small" :loading="busy" @click="save" />
					</template>
				</div>
			</header>
			<Message v-if="isEdited && impact" :severity="data.delivery_days_moved > 0 ? 'error' : 'success'" :closable="false">{{ impact }}</Message>
			<Message v-if="error" severity="error" :closable="true" role="alert" @close="error = ''">{{ error }}</Message>
			<div class="erp-table-wrap ta-editor__scroll" role="region" tabindex="0" aria-label="Time and Action activities">
				<table class="erp-data-table ta-matrix">
					<thead>
						<tr>
							<th class="ta-matrix__sticky">Activity</th>
							<th v-for="row in data.rows" :key="row.action" :title="dependencyTitle(row)">
								<div>{{ row.action }}</div>
								<small>{{ leadTimeLabel(row) }}</small>
							</th>
						</tr>
					</thead>
					<tbody>
						<tr><th class="ta-matrix__sticky">Planned Date</th><td v-for="row in data.rows" :key="row.action">{{ formatDisplayDate(row.planned_start_date, "") }}</td></tr>
						<tr><th class="ta-matrix__sticky">Freezed Date</th><td v-for="row in data.rows" :key="row.action">{{ formatDisplayDate(row.date, "") }}</td></tr>
						<tr>
							<th class="ta-matrix__sticky"><button type="button" class="ta-matrix__link" @click="revisionsVisible = true">Rescheduled Date ({{ data.revised || 0 }})</button></th>
							<td v-for="row in data.rows" :key="row.action">{{ formatDisplayDate(row.rescheduled_date, "") }}</td>
						</tr>
						<tr>
							<th class="ta-matrix__sticky">Actual</th>
							<td v-for="row in data.rows" :key="row.action" :class="`ta-matrix__actual--${actualTone(row)}`">
								<DateField v-if="row.can_enter && canEditRow(data, row)" :model-value="''" :aria-label="`Actual date of ${row.action}`" :disabled="busy" @update:model-value="(value) => setActual(row, value)" />
								<span v-else class="ta-matrix__actual">
									{{ formatDisplayDate(row.actual_date, "") }}
									<Button v-if="row.can_remove && canEditRow(data, row)" icon="pi pi-times" severity="danger" text rounded size="small" :aria-label="`Remove actual date of ${row.action}`" title="Remove" :disabled="busy" @click="removeActual(row)" />
								</span>
							</td>
						</tr>
						<tr>
							<th class="ta-matrix__sticky">Reason for Delay</th>
							<td v-for="row in data.rows" :key="row.action">
								<InputText v-if="row.actual_date && canEditRow(data, row)" v-model="row.reason" size="small" fluid :invalid="isLate(row) && !row.reason" :aria-label="`Reason for delay of ${row.action}`" @change="setReason(row)" />
								<span v-else>{{ row.reason }}</span>
							</td>
						</tr>
						<tr><th class="ta-matrix__sticky">Performance</th><td v-for="row in data.rows" :key="row.action">{{ row.performance }}%</td></tr>
						<tr><th class="ta-matrix__sticky">Delay</th><td v-for="row in data.rows" :key="row.action">{{ row.date_diff }}</td></tr>
						<tr><th class="ta-matrix__sticky">Cumulative Actual Delay</th><td v-for="row in data.rows" :key="row.action">{{ row.actual_delay }}</td></tr>
						<tr><th class="ta-matrix__sticky">Cumulative Rescheduled Delay</th><td v-for="row in data.rows" :key="row.action">{{ row.cumulative_delay }}</td></tr>
					</tbody>
				</table>
			</div>
		</template>
		<DocumentConfirmationDialog v-model:visible="confirmVisible" title="Expected delivery moves" :message="`${impact}. Save anyway?`" confirm-label="Save T&A" cancel-label="Cancel" severity="danger" :busy="busy" @confirm="commit" />
		<DocumentConfirmationDialog v-model:visible="completeVisible" title="Complete T&A" :message="`Complete Time and Action ${data?.name}? Its dates are locked after this.`" confirm-label="Complete T&A" cancel-label="Cancel" severity="success" icon="pi pi-check-circle" :busy="busy" @confirm="complete" />
		<Dialog v-model:visible="reviseVisible" modal header="Revise" class="erp-dialog--sm">
			<div class="ta-editor__revise">
				<p>{{ reviseMessage(data) }}</p>
				<label class="erp-field-label" for="ta-revise-reason">Reason<span class="erp-required-mark" aria-hidden="true">*</span></label>
				<Textarea id="ta-revise-reason" v-model="reviseReason" rows="3" fluid />
				<Message v-if="reviseError" severity="error" :closable="false">{{ reviseError }}</Message>
			</div>
			<template #footer>
				<Button label="Cancel" severity="secondary" text :disabled="busy" @click="reviseVisible = false" />
				<Button label="Revise" icon="pi pi-check" :loading="busy" :disabled="!reviseReason.trim()" @click="revise" />
			</template>
		</Dialog>
		<Dialog v-model:visible="revisionsVisible" modal header="Rescheduled Details" :style="{ width: 'min(1200px, calc(100vw - 32px))' }">
			<div v-if="data" class="erp-table-wrap ta-editor__scroll" role="region" tabindex="0" aria-label="Rescheduled Details">
				<table class="erp-data-table ta-matrix">
					<thead><tr><th class="ta-matrix__sticky" /><th v-for="row in data.rows" :key="row.action">{{ row.action }}</th></tr></thead>
					<tbody>
						<tr><th class="ta-matrix__sticky">Planned Date</th><td v-for="row in data.rows" :key="row.action">{{ formatDisplayDate(row.planned_start_date, "") }}</td></tr>
						<tr><th class="ta-matrix__sticky">Freeze Date</th><td v-for="row in data.rows" :key="row.action">{{ formatDisplayDate(row.date, "") }}</td></tr>
						<tr v-for="revision in revisionRows(data)" :key="revision.label"><th class="ta-matrix__sticky">{{ revision.label }}</th><td v-for="(value, index) in revision.values" :key="index">{{ formatDisplayDate(value, "") }}</td></tr>
						<tr><th class="ta-matrix__sticky">Delay</th><td v-for="row in data.rows" :key="row.action">{{ row.date_diff }}</td></tr>
						<tr><th class="ta-matrix__sticky">Cumulative Actual Delay</th><td v-for="row in data.rows" :key="row.action">{{ row.actual_delay }}</td></tr>
						<tr><th class="ta-matrix__sticky">Cumulative Rescheduled Delay</th><td v-for="row in data.rows" :key="row.action">{{ row.cumulative_delay }}</td></tr>
						<tr><th class="ta-matrix__sticky">Reason</th><td v-for="row in data.rows" :key="row.action">{{ row.reason }}</td></tr>
						<tr><th class="ta-matrix__sticky">Performance</th><td v-for="row in data.rows" :key="row.action">{{ row.performance }}%</td></tr>
					</tbody>
				</table>
			</div>
		</Dialog>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import Tag from "primevue/tag"
import Textarea from "primevue/textarea"
import { useToast } from "primevue/usetoast"
import { computed, ref, watch } from "vue"

import { completeTimeAndAction, getUpdateData, previewActualDates, reviseDates, updateActualDates } from "../../../api/timeAndAction.js"
import DateField from "../../../components/common/DateField.vue"
import DocumentLink from "../../../components/common/DocumentLink.vue"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import { actualTone, canEditRow, deliveryMessage, dependencyTitle, isLate, leadTimeLabel, reviseMessage, revisionRows } from "./timeAndAction.js"

/** One T&A's Desk Update matrix: preview each actual date, then Save T&A; Revise Dates freezes a new baseline. */
const props = defineProps({ name: { type: String, required: true } })
const emit = defineEmits(["saved", "completed"])
const toast = useToast()
const data = ref(null)
const changes = ref({})
const isEdited = ref(false)
const loading = ref(false)
const busy = ref(false)
const loadError = ref("")
const error = ref("")
const confirmVisible = ref(false)
const completeVisible = ref(false)
const reviseVisible = ref(false)
const reviseReason = ref("")
const reviseError = ref("")
const revisionsVisible = ref(false)
const impact = computed(() => deliveryMessage(data.value))
let sequence = 0

async function load() {
	const current = ++sequence
	loading.value = true
	loadError.value = ""
	error.value = ""
	try {
		const payload = await getUpdateData(props.name)
		if (current !== sequence) return
		data.value = payload
		changes.value = {}
		isEdited.value = false
	} catch (reason) {
		if (current === sequence) loadError.value = reason?.message || "Unable to load this Time and Action."
	} finally {
		if (current === sequence) loading.value = false
	}
}

async function preview(action, change) {
	const pending = { ...changes.value, [action]: change }
	busy.value = true
	error.value = ""
	try {
		data.value = await previewActualDates(data.value.name, Object.values(pending), data.value.modified)
		changes.value = pending
		isEdited.value = true
	} catch (reason) {
		error.value = reason?.message || "Unable to apply this date."
	} finally {
		busy.value = false
	}
}

function setActual(row, value) {
	if (value) preview(row.action, { action: row.action, actual_date: value, reason: row.reason || null })
}

function removeActual(row) {
	preview(row.action, { action: row.action, actual_date: null, reason: null })
}

function setReason(row) {
	changes.value = { ...changes.value, [row.action]: { action: row.action, actual_date: row.actual_date, reason: row.reason || null } }
	isEdited.value = true
}

function save() {
	if (data.value.delivery_days_moved > 0) confirmVisible.value = true
	else commit()
}

async function commit() {
	busy.value = true
	error.value = ""
	try {
		await updateActualDates(data.value.name, Object.values(changes.value), data.value.modified)
		confirmVisible.value = false
		toast.add({ severity: "success", summary: "T&A saved", life: 3000 })
		await load()
		emit("saved")
	} catch (reason) {
		confirmVisible.value = false
		error.value = reason?.message || "Unable to save this Time and Action."
	} finally {
		busy.value = false
	}
}

async function complete() {
	busy.value = true
	error.value = ""
	try {
		await completeTimeAndAction(data.value.name)
		completeVisible.value = false
		toast.add({ severity: "success", summary: `${data.value.name} completed`, life: 3000 })
		emit("completed", data.value.name)
	} catch (reason) {
		completeVisible.value = false
		error.value = reason?.message || "Unable to complete this Time and Action."
	} finally {
		busy.value = false
	}
}

async function revise() {
	busy.value = true
	reviseError.value = ""
	try {
		await reviseDates(data.value.name, reviseReason.value.trim())
		reviseVisible.value = false
		reviseReason.value = ""
		toast.add({ severity: "success", summary: "Dates revised", life: 3000 })
		await load()
		emit("saved")
	} catch (reason) {
		reviseError.value = reason?.message || "Unable to revise the dates."
	} finally {
		busy.value = false
	}
}

watch(() => props.name, () => { data.value = null; load() }, { immediate: true })
</script>

<style scoped>
.ta-editor { display: grid; min-width: 0; gap: var(--erp-space-3); }
.ta-editor__bar { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--erp-space-3); align-items: center; }
.ta-editor__summary { display: flex; flex-wrap: wrap; gap: var(--erp-space-2) var(--erp-space-5); }
.ta-editor__actions { display: flex; flex-wrap: wrap; gap: var(--erp-space-2); align-items: center; }
.ta-editor__late { color: var(--erp-danger); }
.ta-editor__scroll { max-height: 70vh; overflow: auto; }
.ta-editor__revise { display: grid; gap: var(--erp-space-2); }
.ta-editor__revise p { margin: 0; }
.ta-matrix th, .ta-matrix td { min-width: 140px; text-align: center; vertical-align: middle; }
.ta-matrix thead th small { display: block; color: var(--erp-text-muted); font-weight: 400; }
.ta-matrix .ta-matrix__sticky { position: sticky; left: 0; z-index: 1; min-width: 200px; text-align: left; background: var(--erp-surface); }
.ta-matrix thead .ta-matrix__sticky { z-index: 3; }
.ta-matrix__link { padding: 0; border: 0; background: none; color: var(--erp-accent); font: inherit; font-weight: 600; cursor: pointer; text-align: left; }
.ta-matrix__actual { display: inline-flex; gap: var(--erp-space-1); align-items: center; }
.ta-matrix__actual--late { background: var(--erp-danger-soft); }
.ta-matrix__actual--on-time { background: var(--erp-success-soft); }
</style>
