<template>
	<Dialog :visible="visible" modal :dismissable-mask="false" header="Create Work Order Correction" class="fabric-action-dialog erp-dialog--lg work-order-correction-dialog" @update:visible="close">
		<div class="work-order-correction">
			<Message severity="secondary" :closable="false">Add the extra deliverables and receivables for {{ workOrder.name }}. The correction is submitted immediately and its rows appear on the Delivery Challan and Goods Received Note for quantity entry.</Message>
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<label class="work-order-correction__reason"><span>Reason</span><Textarea v-model="reason" rows="2" auto-resize :disabled="busy" aria-label="Correction reason" /></label>
			<section class="work-order-correction__section"><header><span>Inputs</span><h2>Deliverables</h2></header><StockItemComposer v-model="deliverableDetails" operation="work_order" :editor="itemEditor" :schema-loader="loadItemSchema" :disabled="busy" row-comments natural-table-flow /></section>
			<section class="work-order-correction__section"><header><span>Outputs</span><h2>Receivables</h2></header><StockItemComposer v-model="receivableDetails" operation="work_order" :editor="itemEditor" :schema-loader="loadItemSchema" :disabled="busy" row-comments natural-table-flow /></section>
		</div>
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="busy" @click="close(false)" />
			<Button label="Submit Correction" icon="pi pi-check" :loading="busy" :disabled="!hasRows" @click="submit" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Textarea from "primevue/textarea"
import { computed, ref, watch } from "vue"

import { executeWorkOrderCommand, getWorkOrderItemSchema } from "../../api/fabricStore.js"
import StockItemComposer from "../../components/stock/StockItemComposer.vue"
import { correctionItemEditor, hasCorrectionRows } from "./workOrderCorrection.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	workOrder: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:visible", "changed"])

const reason = ref("")
const deliverableDetails = ref([])
const receivableDetails = ref([])
const itemEditor = correctionItemEditor()
const busy = ref(false)
const error = ref("")
const hasRows = computed(() => hasCorrectionRows(deliverableDetails.value) || hasCorrectionRows(receivableDetails.value))

watch(() => props.visible, (visible) => { if (visible) reset() })

function reset() {
	reason.value = ""
	deliverableDetails.value = []
	receivableDetails.value = []
	error.value = ""
}

function loadItemSchema(_operation, item) { return getWorkOrderItemSchema(item) }

function close(visible) { if (!busy.value) emit("update:visible", Boolean(visible)) }

async function submit() {
	busy.value = true
	error.value = ""
	try {
		const result = await executeWorkOrderCommand(props.workOrder.name, "create_work_order_correction", {
			deliverable_details: deliverableDetails.value,
			receivable_details: receivableDetails.value,
			reason: reason.value,
		}, props.workOrder.modified)
		emit("changed", result)
		emit("update:visible", false)
	}
	catch (failure) { error.value = failure?.message || "Unable to submit the Work Order Correction." }
	finally { busy.value = false }
}
</script>

<style scoped>
.work-order-correction { display: grid; gap: var(--erp-space-3); }
.work-order-correction__reason { display: grid; gap: 4px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; }
.work-order-correction__section { display: grid; gap: var(--erp-space-2); }
.work-order-correction__section header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .035em; text-transform: uppercase; }
.work-order-correction__section header h2 { margin: 0; font-size: 16px; }
</style>
