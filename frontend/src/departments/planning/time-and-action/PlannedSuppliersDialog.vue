<template>
	<Dialog :visible="visible" modal :header="`Planned Suppliers · ${action}`" class="erp-dialog--sm" :closable="!busy" @update:visible="emit('update:visible', $event)" @show="suppliers = [...initial]; error = ''">
		<div class="ta-planned">
			<p>For information only: where this action is planned. Quantities and dates do not change.</p>
			<LinkMultiSelectField v-model="suppliers" doctype="Supplier" label="Planned Suppliers" input-id="ta-planned-suppliers" placeholder="None" display="chip" />
			<Message v-if="error" severity="error" :closable="false" role="alert">{{ error }}</Message>
		</div>
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="busy" @click="emit('update:visible', false)" />
			<Button label="Save" icon="pi pi-check" :loading="busy" @click="save" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import { ref } from "vue"

import LinkMultiSelectField from "../../../components/common/LinkMultiSelectField.vue"

/** Edit the planned suppliers of one action; `onSave(suppliers)` saves them on the server. */
const props = defineProps({
	visible: { type: Boolean, default: false },
	action: { type: String, default: "" },
	initial: { type: Array, default: () => [] },
	onSave: { type: Function, required: true },
})
const emit = defineEmits(["update:visible"])
const suppliers = ref([])
const busy = ref(false)
const error = ref("")

async function save() {
	busy.value = true
	error.value = ""
	try {
		await props.onSave(suppliers.value)
		emit("update:visible", false)
	} catch (reason) {
		error.value = reason?.message || "Unable to save the planned suppliers."
	} finally {
		busy.value = false
	}
}
</script>

<style scoped>
.ta-planned { display: grid; gap: var(--erp-space-3); }
.ta-planned p { margin: 0; }
</style>
