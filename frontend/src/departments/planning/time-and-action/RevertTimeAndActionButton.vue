<template>
	<template v-if="data.can_revert">
		<Button label="Revert T&A" icon="pi pi-undo" severity="danger" outlined size="small" :disabled="disabled || busy" title="Delete this T&A and all its dates" @click="visible = true" />
		<DocumentConfirmationDialog v-model:visible="visible" :title="`Revert ${data.name}?`" :message="getRevertMessage(data.name, againstLabel(data.against))" confirm-label="Revert T&A" confirm-icon="pi pi-undo" cancel-label="Cancel" severity="danger" :busy="busy" @confirm="revert" />
	</template>
</template>

<script setup>
import Button from "primevue/button"
import { useToast } from "primevue/usetoast"
import { ref } from "vue"

import { revertTimeAndAction } from "../../../api/timeAndAction.js"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import { againstLabel, getRevertMessage } from "./timeAndAction.js"

/** T&A Admin's Revert T&A: confirm, delete the T&A, then emit `reverted` with its name. */
const props = defineProps({
	data: { type: Object, required: true },
	disabled: { type: Boolean, default: false },
})
const emit = defineEmits(["reverted"])
const toast = useToast()
const visible = ref(false)
const busy = ref(false)

async function revert() {
	const name = props.data.name
	busy.value = true
	try {
		await revertTimeAndAction(name)
		visible.value = false
		toast.add({ severity: "success", summary: `${name} reverted. Create T&A is available again.`, life: 4000 })
		emit("reverted", name)
	} catch (reason) {
		toast.add({ severity: "error", summary: reason?.message || `Unable to revert ${name}.`, life: 6000 })
	} finally {
		busy.value = false
	}
}
</script>
