<template>
	<Dialog :visible="visible" modal header="Convert to Lot T&A" :closable="!busy" :style="{ width: 'min(640px, calc(100vw - 32px))' }" @update:visible="emit('update:visible', $event)" @show="load">
		<div class="ta-convert">
			<template v-if="created.length">
				<Message severity="success" :closable="false">Lot T&A created. {{ timeAndAction }} is frozen.</Message>
				<ul class="ta-convert__list">
					<li v-for="(name, index) in created" :key="name"><DocumentLink doctype="SD YRP Time and Action" :name="name" /> · {{ createdLots[index] }}</li>
				</ul>
			</template>
			<template v-else>
				<p class="ta-convert__info">Each selected Lot gets a copy of <b>{{ timeAndAction }}</b>: rows, dependencies, work stations, dates, actual dates and reasons. The Production Order T&A is then frozen.</p>
				<Skeleton v-if="loading" height="96px" />
				<p v-else-if="!lots.length && !error" class="ta-convert__info ta-convert__subtle">Every Lot linked to this Production Order already has a Time and Action, or none is linked.</p>
				<fieldset v-else-if="lots.length" class="ta-convert__lots">
					<legend>Lots</legend>
					<label v-for="lot in lots" :key="lot.name" class="ta-convert__lot">
						<Checkbox :model-value="selected.includes(lot.name)" binary :input-id="`ta-convert-${lot.name}`" :disabled="busy" @update:model-value="selected = toggleLot(selected, lot.name, lots)" />
						<span>{{ lotOptionLabel(lot) }}</span>
					</label>
				</fieldset>
				<Message v-if="confirming" severity="warn" :closable="false">{{ convertConfirmMessage(timeAndAction, selected) }}</Message>
				<Message v-if="error" severity="error" :closable="false" role="alert">{{ error }}</Message>
			</template>
		</div>
		<template #footer>
			<Button v-if="created.length" label="Close" @click="emit('update:visible', false)" />
			<template v-else>
				<Button label="Cancel" severity="secondary" outlined :disabled="busy" @click="confirming ? (confirming = false) : emit('update:visible', false)" />
				<Button v-if="confirming" label="Convert" icon="pi pi-check" :loading="busy" @click="convert" />
				<Button v-else label="Continue" :disabled="!selected.length" @click="confirming = true" />
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
import { ref } from "vue"

import { convertToLotTimeAndAction, getConvertibleLots } from "../../../api/timeAndAction.js"
import DocumentLink from "../../../components/common/DocumentLink.vue"
import { convertConfirmMessage, lotOptionLabel, toggleLot } from "./productionOrderTimeAndAction.js"

/** Convert to Lot T&A: pick linked Lots without a T&A, confirm, then links to the created T&As. */
const props = defineProps({
	visible: { type: Boolean, default: false },
	timeAndAction: { type: String, required: true },
})
const emit = defineEmits(["update:visible", "converted"])
const lots = ref([])
const selected = ref([])
const created = ref([])
const createdLots = ref([])
const confirming = ref(false)
const loading = ref(false)
const busy = ref(false)
const error = ref("")

async function load() {
	lots.value = []
	selected.value = []
	created.value = []
	confirming.value = false
	error.value = ""
	loading.value = true
	try {
		lots.value = await getConvertibleLots(props.timeAndAction) || []
	} catch (reason) {
		error.value = reason?.message || "Unable to load the linked Lots."
	} finally {
		loading.value = false
	}
}

async function convert() {
	busy.value = true
	error.value = ""
	try {
		createdLots.value = [...selected.value]
		created.value = await convertToLotTimeAndAction(props.timeAndAction, selected.value) || []
		emit("converted", created.value)
	} catch (reason) {
		error.value = reason?.message || "Unable to convert to Lot T&A."
		confirming.value = false
	} finally {
		busy.value = false
	}
}
</script>

<style scoped>
.ta-convert { display: grid; min-width: 0; gap: var(--erp-space-3); }
.ta-convert__info { margin: 0; }
.ta-convert__subtle { color: var(--erp-text-subtle); }
.ta-convert__lots { display: grid; gap: 8px; margin: 0; padding: 10px 12px; border: 1px solid var(--erp-border); border-radius: var(--erp-radius-md); }
.ta-convert__lots legend { padding: 0 4px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
.ta-convert__lot { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.ta-convert__list { display: grid; gap: 6px; margin: 0; padding-left: 18px; }
</style>
