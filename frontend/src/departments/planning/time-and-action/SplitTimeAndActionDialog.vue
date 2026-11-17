<template>
	<Dialog :visible="visible" modal header="Split T&A" :closable="!busy" :style="{ width: 'min(640px, calc(100vw - 32px))' }" @update:visible="emit('update:visible', $event)" @show="load">
		<div class="ta-split">
			<template v-if="created.length">
				<Message severity="success" :closable="false">Lot T&A created. {{ timeAndAction }} continues.</Message>
				<ul class="ta-split__list">
					<li v-for="(name, index) in created" :key="name"><b>{{ name }}</b> · {{ createdLots[index] }}</li>
				</ul>
			</template>
			<template v-else>
				<p class="ta-split__info">Each selected Lot gets a copy of <b>{{ timeAndAction }}</b>: rows, dependencies, work stations, dates, actual dates and reasons. This T&A continues, and each Lot is updated on its own.</p>
				<Skeleton v-if="loading && !lots.length" height="40px" />
				<MultiSelectField
					v-else
					v-model="selected"
					label="Lots"
					:options="options"
					option-label="label"
					option-value="value"
					placeholder="Search Lots without a T&A"
					help-text="Lots with their own T&A, or linked to a Production Order with a T&A, are not listed."
					:disabled="busy"
					:loading="loading"
					:max-selected-labels="6"
					:show-toggle-all="false"
					@filter="search"
				/>
				<Message v-if="confirming" severity="warn" :closable="false">{{ splitConfirmMessage(timeAndAction, selected) }}</Message>
				<Message v-if="error" severity="error" :closable="false" role="alert">{{ error }}</Message>
			</template>
		</div>
		<template #footer>
			<Button v-if="created.length" label="Close" @click="emit('update:visible', false)" />
			<template v-else>
				<Button label="Cancel" severity="secondary" outlined :disabled="busy" @click="confirming ? (confirming = false) : emit('update:visible', false)" />
				<Button v-if="confirming" label="Split" icon="pi pi-check" :loading="busy" @click="split" />
				<Button v-else label="Continue" :disabled="!selected.length" @click="confirming = true" />
			</template>
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, ref } from "vue"

import { getSplitLots, splitTimeAndAction } from "../../../api/timeAndAction.js"
import MultiSelectField from "../../../components/common/MultiSelectField.vue"
import { lotOptionLabel } from "./productionOrderTimeAndAction.js"
import { mergeLotOptions, splitConfirmMessage } from "./splitTimeAndAction.js"

/** Split T&A: search Lots without a T&A, confirm, then links to the created T&As; the source continues. */
const props = defineProps({
	visible: { type: Boolean, default: false },
	timeAndAction: { type: String, required: true },
})
const emit = defineEmits(["update:visible", "split"])
const lots = ref([])
const selected = ref([])
const created = ref([])
const createdLots = ref([])
const confirming = ref(false)
const loading = ref(false)
const busy = ref(false)
const error = ref("")
const options = computed(() => lots.value.map((lot) => ({ value: lot.name, label: lot.item ? lotOptionLabel(lot) : lot.name })))
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

async function split() {
	busy.value = true
	error.value = ""
	try {
		createdLots.value = [...selected.value]
		created.value = await splitTimeAndAction(props.timeAndAction, selected.value) || []
		emit("split", created.value)
	} catch (reason) {
		error.value = reason?.message || "Unable to split the T&A."
		confirming.value = false
	} finally {
		busy.value = false
	}
}
</script>

<style scoped>
.ta-split { display: grid; min-width: 0; gap: var(--erp-space-3); }
.ta-split__info { margin: 0; }
.ta-split :deep(.common-field), .ta-split :deep(.p-multiselect-label-container) { min-width: 0; }
.ta-split :deep(.p-multiselect-label) { flex-wrap: wrap; white-space: normal; }
.ta-split__list { display: grid; gap: 6px; margin: 0; padding-left: 18px; }
</style>
