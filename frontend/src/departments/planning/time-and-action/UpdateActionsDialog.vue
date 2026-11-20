<template>
	<Dialog :visible="visible" modal :header="`Update Action · ${name}`" :closable="!busy" :breakpoints="{ '640px': '95vw' }" :style="{ width: 'min(920px, calc(100vw - 32px))' }" @update:visible="emit('update:visible', $event)" @show="reset">
		<div class="ta-steps">
			<p class="ta-steps__info">Completed actions are locked. Remove actions that are not dated yet, change what they depend on, or add new ones after the last completed action. Nothing is saved until you confirm.</p>
			<div class="ta-steps__scroll">
				<table class="erp-data-table ta-steps__table">
					<thead><tr><th class="erp-number">#</th><th>Action</th><th class="erp-number">Lead Time</th><th>Rescheduled Date</th><th class="ta-steps__depends">Depends On</th><th class="ta-steps__control" /></tr></thead>
					<tbody>
						<tr v-for="(row, index) in rows" :key="row.action" :class="{ 'is-done': row.actual_date, 'is-new': isNew(row.action) }">
							<td class="erp-number ta-steps__index">{{ index + 1 }}</td>
							<td class="ta-steps__action"><b>{{ row.action }}</b><span v-if="isNew(row.action)" class="ta-steps__tag">New</span></td>
							<td class="erp-number ta-steps__lead" data-label="Lead Time">{{ row.lead_time }}</td>
							<td class="ta-steps__date" data-label="Rescheduled Date">
								<span v-if="row.actual_date"><i class="pi pi-lock" aria-hidden="true" /> Done {{ formatDisplayDate(row.actual_date, "") }}</span>
								<template v-else>{{ formatDisplayDate(row.rescheduled_date, "") }}</template>
							</td>
							<td class="ta-steps__depends" data-label="Depends On">
								<MultiSelectField v-if="!row.actual_date && !isNew(row.action)" :model-value="dependsOnFor(row)" :options="getEditDependsOnOptions(rows, row.action).map(asOption)" placeholder="None" display="comma" :max-selected-labels="2" :aria-label="`${row.action} depends on`" @update:model-value="changeDependsOn(row.action, $event)" />
								<span v-else class="ta-steps__muted">{{ getDependsOn(row).join(", ") || "None" }}</span>
							</td>
							<td class="ta-steps__control">
								<Button v-if="!row.actual_date" :icon="isNew(row.action) ? 'pi pi-undo' : 'pi pi-trash'" text rounded size="small" :severity="isNew(row.action) ? 'secondary' : 'danger'" :disabled="busy" :aria-label="`${isNew(row.action) ? 'Undo add of' : 'Remove'} ${row.action}`" :title="isNew(row.action) ? 'Undo add' : 'Remove action'" @click="removeRow(row.action)" />
							</td>
						</tr>
					</tbody>
				</table>
			</div>
			<div v-if="removes.length" class="ta-steps__removed">
				<span>Removing:</span>
				<Button v-for="action in removes" :key="action" :label="action" icon="pi pi-undo" size="small" severity="secondary" outlined :disabled="busy" :title="`Keep ${action}`" @click="undoRemove(action)" />
			</div>
			<section class="ta-steps__form" aria-label="Add an action">
				<LinkField v-model="form.action" doctype="SD YRP Action" label="Action" required :show-open-button="false" />
				<label class="ta-steps__field"><span class="erp-field-label">Lead Time (days)</span><InputNumber v-model="form.lead_time" :min="1" show-buttons size="small" fluid input-id="ta-steps-lead-time" /></label>
				<label class="ta-steps__field"><span class="erp-field-label">Position</span><Select v-model="form.after_action" :options="slots" option-label="label" option-value="value" size="small" fluid aria-label="Position" /></label>
				<LinkField v-model="form.work_station" doctype="YRP Work Station" label="Work Station" :filters="{ action: form.action || '' }" :disabled="!form.action" :allow-create="false" :show-open-button="false" show-clear />
				<MultiSelectField v-model="form.depends_on" :options="dependsOnOptions.map(asOption)" label="Depends On" placeholder="Actions it waits for" />
				<MultiSelectField v-model="form.required_by" :options="requiredByOptions.map(asOption)" label="Must finish before" placeholder="Optional" />
				<div class="ta-steps__add"><Button label="Add to list" icon="pi pi-plus" size="small" outlined :disabled="!canAdd" @click="addRow" /></div>
			</section>
			<ul v-if="summary.length" class="ta-steps__summary"><li v-for="line in summary" :key="line">{{ line }}</li></ul>
			<span class="ta-impact" :class="`ta-impact--${impact.tone}`">
				<template v-if="impact.from"><i :class="impact.tone === 'late' ? 'pi pi-exclamation-circle' : 'pi pi-check'" aria-hidden="true" />Expected delivery moves {{ impact.from }} <i class="pi pi-arrow-right" aria-hidden="true" /> {{ impact.to }}, <b>{{ impact.text }}</b></template>
				<template v-else>{{ summary.length ? impact.text : "Add, remove or re-link actions to see the effect on delivery" }}</template>
			</span>
			<Message v-if="error" severity="error" :closable="false" role="alert">{{ error }}</Message>
		</div>
		<template #footer>
			<Button label="Cancel" severity="secondary" outlined :disabled="busy" @click="emit('update:visible', false)" />
			<Button label="Confirm" icon="pi pi-check" :loading="busy" :disabled="!summary.length || Boolean(error)" @click="confirm" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import Message from "primevue/message"
import Select from "primevue/select"
import { computed, reactive, ref, watch } from "vue"

import { getActionLeadTime, previewUpdateActions, updateActions } from "../../../api/timeAndActionSteps.js"
import LinkField from "../../../components/common/LinkField.vue"
import MultiSelectField from "../../../components/common/MultiSelectField.vue"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import { getImpact } from "./timeAndAction.js"
import {
	describeActionChanges, getDependsOn, getDependsOnOptions, getEditDependsOnOptions, getInsertSlots, getRequiredByOptions,
	pruneEditsForRemove, setDependencyEdit,
} from "./timeAndActionSteps.js"

/** One dialog to add, remove and re-link T&A actions; the server previews every change and Confirm saves them together. */
const props = defineProps({
	visible: { type: Boolean, default: false },
	name: { type: String, required: true },
	data: { type: Object, required: true },
})
const emit = defineEmits(["update:visible", "saved"])
const adds = ref([])
const removes = ref([])
const edits = ref([])
const preview = ref(null)
const error = ref("")
const busy = ref(false)
let previewRequest = 0
const form = reactive(emptyForm())

const rows = computed(() => preview.value?.rows || props.data.rows)
const slots = computed(() => getInsertSlots(rows.value))
const dependsOnOptions = computed(() => getDependsOnOptions(rows.value, form.after_action))
const requiredByOptions = computed(() => getRequiredByOptions(rows.value, form.after_action))
const summary = computed(() => describeActionChanges(adds.value, removes.value, edits.value))
const impact = computed(() => getImpact(preview.value, summary.value.length > 0))
const canAdd = computed(() => Boolean(form.action && form.lead_time >= 1 && !busy.value && !rows.value.some((row) => row.action === form.action)))

function emptyForm() {
	return { action: "", lead_time: 1, after_action: null, depends_on: [], required_by: [], work_station: "" }
}

function reset() {
	adds.value = []
	removes.value = []
	edits.value = []
	preview.value = null
	error.value = ""
	resetForm()
}

function resetForm() {
	Object.assign(form, emptyForm(), { after_action: slots.value[0]?.value ?? null })
	form.depends_on = form.after_action ? [form.after_action] : []
}

watch(() => form.action, async (action) => {
	form.work_station = ""
	if (action) form.lead_time = await getActionLeadTime(action)
})

watch(() => form.after_action, (after) => {
	form.depends_on = after ? [after] : []
	form.required_by = form.required_by.filter((action) => requiredByOptions.value.includes(action))
})

const asOption = (action) => ({ label: action, value: action })
const isNew = (action) => adds.value.some((item) => item.action === action)
const dependsOnFor = (row) => edits.value.find((edit) => edit.action === row.action)?.depends_on || getDependsOn(row)

async function refresh(nextAdds, nextRemoves, nextEdits = edits.value) {
	const request = ++previewRequest
	busy.value = true
	error.value = ""
	try {
		const hasChanges = nextAdds.length || nextRemoves.length || nextEdits.length
		const result = hasChanges ? await previewUpdateActions(props.name, nextAdds, nextRemoves, nextEdits) : null
		if (request !== previewRequest) return false
		preview.value = result
		adds.value = nextAdds
		removes.value = nextRemoves
		edits.value = nextEdits
		return true
	} catch (reason) {
		if (request === previewRequest) error.value = reason?.message || "Unable to apply this change."
		return false
	} finally {
		if (request === previewRequest) busy.value = false
	}
}

async function changeDependsOn(action, dependsOn) {
	const previous = edits.value
	edits.value = setDependencyEdit(previous, props.data.rows, action, dependsOn)
	if (!(await refresh(adds.value, removes.value, edits.value)) && error.value) edits.value = previous
}

async function addRow() {
	const item = { ...form, depends_on: [...form.depends_on], required_by: [...form.required_by], work_station: form.work_station || null }
	if (await refresh([...adds.value, item], removes.value)) resetForm()
}

function removeRow(action) {
	const nextEdits = pruneEditsForRemove(edits.value, action)
	if (isNew(action)) refresh(adds.value.filter((item) => item.action !== action), removes.value, nextEdits)
	else refresh(adds.value, [...removes.value, action], nextEdits)
}

function undoRemove(action) {
	refresh(adds.value, removes.value.filter((item) => item !== action))
}

async function confirm() {
	busy.value = true
	error.value = ""
	try {
		await updateActions(props.name, adds.value, removes.value, edits.value)
		emit("update:visible", false)
		emit("saved", summary.value)
	} catch (reason) {
		error.value = reason?.message || "Unable to update the actions."
	} finally {
		busy.value = false
	}
}
</script>

<style scoped>
.ta-steps { display: grid; gap: 12px; }
.ta-steps__info { margin: 0; color: var(--erp-text-muted); font-size: 13px; }
.ta-steps__scroll { max-height: 300px; overflow: auto; border: 1px solid var(--erp-border); border-radius: 7px; }
.ta-steps__table td { padding: 6px 10px; }
.ta-steps__table tr.is-done td { color: var(--erp-text-muted); background: color-mix(in srgb, var(--erp-success-soft) 70%, transparent); }
.ta-steps__table tr.is-new td { background: color-mix(in srgb, var(--erp-attention-soft) 45%, transparent); }
.ta-steps__control { width: 48px; text-align: right; }
.ta-steps__depends { width: 280px; min-width: 220px; }
.ta-steps__depends :deep(.p-multiselect) { max-width: 260px; }
.ta-steps__date { white-space: nowrap; }
.ta-steps__muted { color: var(--erp-text-muted); font-size: 13px; }
.ta-steps__tag { margin-left: 8px; padding: 1px 6px; color: var(--erp-attention-text); font-size: var(--erp-font-size-caption); font-weight: 600; background: var(--erp-attention-soft); border-radius: 5px; }
.ta-steps__removed { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: 13px; color: var(--erp-danger); }
.ta-steps__form { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px 14px; align-items: end; padding: 12px; background: var(--erp-surface-soft); border: 1px solid var(--erp-border); border-radius: 7px; }
.ta-steps__field { display: grid; gap: 4px; }
.ta-steps__add { display: flex; justify-content: flex-end; }
.ta-steps__summary { margin: 0; padding-left: 18px; font-size: 13px; }
.ta-impact { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 7px; justify-self: start; padding: 5px 10px; font-size: 13px; font-weight: 500; border-radius: 7px; }
.ta-impact--late { color: var(--erp-attention-text); background: var(--erp-attention-soft); border: 1px solid var(--erp-attention-border); }
.ta-impact--early { color: var(--erp-success-text); background: var(--erp-success-soft); }
.ta-impact--none { color: var(--erp-text-muted); }
@media (max-width: 640px) {
	.ta-steps__form { grid-template-columns: minmax(0, 1fr); padding: 10px; }
	.ta-steps__scroll { max-height: 50vh; border: 0; }
	.ta-steps__table, .ta-steps__table > tbody { display: block; min-width: 0; }
	.ta-steps__table > thead { display: none; }
	.ta-steps__table > tbody > tr { display: grid; grid-template-columns: 24px minmax(0, 1fr) minmax(0, 1fr) 40px; grid-template-areas: "index action action control" ". lead date date" ". depends depends depends"; gap: 6px 10px; margin-bottom: 6px; padding: 8px 10px; border: 1px solid var(--erp-border); border-radius: 7px; }
	.ta-steps__table > tbody > tr.is-done { background: color-mix(in srgb, var(--erp-success-soft) 70%, transparent); }
	.ta-steps__table > tbody > tr.is-new { background: color-mix(in srgb, var(--erp-attention-soft) 45%, transparent); }
	.ta-steps__table.erp-data-table > tbody > tr > td { display: block; min-width: 0; width: auto; padding: 0; text-align: left; background: none; border: 0; }
	.ta-steps__table td[data-label]::before { content: attr(data-label); display: block; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
	.ta-steps__table td.ta-steps__index { grid-area: index; align-self: center; color: var(--erp-text-muted); }
	.ta-steps__table td.ta-steps__action { grid-area: action; align-self: center; }
	.ta-steps__table td.ta-steps__lead { grid-area: lead; }
	.ta-steps__table td.ta-steps__date { grid-area: date; }
	.ta-steps__table td.ta-steps__depends { grid-area: depends; }
	.ta-steps__table td.ta-steps__control { grid-area: control; }
	.ta-steps__depends :deep(.p-multiselect) { max-width: none; width: 100%; min-height: 40px; }
	.ta-steps__control :deep(.p-button) { width: 40px; height: 40px; }
	.ta-steps__add { justify-content: flex-start; }
}
</style>
