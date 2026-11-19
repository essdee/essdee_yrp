<template>
	<Dialog :visible="visible" modal header="Split T&A" :closable="!busy" :style="{ width: 'min(640px, calc(100vw - 32px))' }" @update:visible="emit('update:visible', $event)" @show="load">
		<div class="ta-split">
			<template v-if="created.length">
				<Message severity="success" :closable="false">Lot T&A created.</Message>
				<ul class="ta-split__list">
					<li v-for="(name, index) in created" :key="name"><b>{{ name }}</b> · {{ createdLots[index] }}</li>
				</ul>
			</template>
			<template v-else-if="confirming">
				<div class="ta-split__lots"><span class="erp-field-label">Lots</span> {{ selected.join(", ") }}</div>
				<Skeleton v-if="loadingRows" height="120px" />
				<template v-else-if="datedActions.length">
					<span class="erp-field-label">Copy Actual Dates</span>
					<table class="ta-split__table">
						<thead><tr><th><Checkbox :model-value="copied.length === datedActions.length" binary :disabled="busy" aria-label="Copy all actual dates" @update:model-value="copied = $event ? datedActions.map((row) => row.action) : []" /></th><th>Action</th><th>Actual Date</th></tr></thead>
						<tbody>
							<tr v-for="row in datedActions" :key="row.action">
								<td><Checkbox :model-value="copied.includes(row.action)" binary :disabled="busy" :input-id="`ta-split-${row.action}`" @update:model-value="toggle(row.action, $event)" /></td>
								<td><label :for="`ta-split-${row.action}`">{{ row.action }}</label></td>
								<td>{{ formatDisplayDate(row.actual_date) }}</td>
							</tr>
						</tbody>
					</table>
					<small v-if="note" class="ta-split__note">{{ note }}</small>
				</template>
			</template>
			<template v-else>
				<Skeleton v-if="loading && !lots.length" height="40px" />
				<MultiSelectField
					v-else
					v-model="selected"
					label="Lots"
					:options="options"
					option-label="label"
					option-value="value"
					placeholder="Search Lots without a T&A"
					:disabled="busy"
					:loading="loading"
					:max-selected-labels="6"
					:show-toggle-all="false"
					@filter="search"
				/>
			</template>
			<Message v-if="error" severity="error" :closable="false" role="alert">{{ error }}</Message>
		</div>
		<template #footer>
			<Button v-if="created.length" label="Close" @click="emit('update:visible', false)" />
			<template v-else>
				<Button label="Cancel" severity="secondary" outlined :disabled="busy" @click="confirming ? (confirming = false) : emit('update:visible', false)" />
				<Button v-if="confirming" label="Split" icon="pi pi-check" :loading="busy" :disabled="loadingRows" @click="split" />
				<Button v-else label="Continue" :disabled="!selected.length" @click="openConfirm" />
			</template>
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, ref } from "vue"

import { getSplitLots, getUpdateData, splitTimeAndAction } from "../../../api/timeAndAction.js"
import MultiSelectField from "../../../components/common/MultiSelectField.vue"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import { lotOptionLabel } from "./productionOrderTimeAndAction.js"
import { getDatedActions, mergeLotOptions, setActualCopied, splitCopyNote } from "./splitTimeAndAction.js"

/** Split T&A: pick Lots, choose which actual dates to copy, then links to the created T&As; the source continues. */
const props = defineProps({
	visible: { type: Boolean, default: false },
	timeAndAction: { type: String, required: true },
})
const emit = defineEmits(["update:visible", "split"])
const lots = ref([])
const selected = ref([])
const created = ref([])
const createdLots = ref([])
const datedActions = ref([])
const copied = ref([])
const note = ref("")
const confirming = ref(false)
const loading = ref(false)
const loadingRows = ref(false)
const busy = ref(false)
const error = ref("")
const options = computed(() => lots.value.map((lot) => ({ value: lot.name, label: lot.item ? lotOptionLabel(lot) : lot.name })))
const skippedActions = computed(() => datedActions.value.map((row) => row.action).filter((action) => !copied.value.includes(action)))
let searchTimer = null
let sequence = 0

async function fetchLots(txt) {
	const current = ++sequence
	loading.value = true
	error.value = ""
	try {
		const found = await getSplitLots(props.timeAndAction, txt) || []
		if (current === sequence) lots.value = mergeLotOptions(lots.value, found, selected.value)
	} catch (reason) {
		if (current === sequence) error.value = reason?.message || "Unable to load the Lots."
	} finally {
		if (current === sequence) loading.value = false
	}
}

function load() {
	lots.value = []
	selected.value = []
	created.value = []
	confirming.value = false
	fetchLots("")
}

function search(event) {
	clearTimeout(searchTimer)
	searchTimer = setTimeout(() => fetchLots(event?.value || ""), 300)
}

async function openConfirm() {
	confirming.value = true
	loadingRows.value = true
	error.value = ""
	note.value = ""
	try {
		datedActions.value = getDatedActions((await getUpdateData(props.timeAndAction))?.rows || [])
		copied.value = datedActions.value.map((row) => row.action)
	} catch (reason) {
		error.value = reason?.message || "Unable to load the actual dates."
		confirming.value = false
	} finally {
		loadingRows.value = false
	}
}

function toggle(action, checked) {
	const result = setActualCopied(datedActions.value, copied.value, action, checked)
	copied.value = result.copied
	note.value = result.also.length ? splitCopyNote(action, checked, result.also) : ""
}

async function split() {
	busy.value = true
	error.value = ""
	try {
		createdLots.value = [...selected.value]
		created.value = await splitTimeAndAction(props.timeAndAction, selected.value, skippedActions.value) || []
		emit("split", created.value)
	} catch (reason) {
		error.value = reason?.message || "Unable to split the T&A."
	} finally {
		busy.value = false
	}
}
</script>

<style scoped>
.ta-split { display: grid; min-width: 0; gap: var(--erp-space-3); }
.ta-split :deep(.common-field), .ta-split :deep(.p-multiselect-label-container) { min-width: 0; }
.ta-split :deep(.p-multiselect-label) { flex-wrap: wrap; white-space: normal; }
.ta-split__list { display: grid; gap: 6px; margin: 0; padding-left: 18px; }
.ta-split__lots { overflow-wrap: anywhere; }
.ta-split__table { width: 100%; border-collapse: collapse; }
.ta-split__table th, .ta-split__table td { padding: 6px 8px; border-bottom: 1px solid var(--erp-border, #e5e7eb); text-align: left; }
.ta-split__table th:first-child, .ta-split__table td:first-child { width: 40px; }
.ta-split__note { color: var(--erp-text-muted, #6b7280); }
</style>
