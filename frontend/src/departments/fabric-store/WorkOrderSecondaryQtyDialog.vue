<template>
	<Dialog :visible="visible" modal :dismissable-mask="false" header="Secondary Qty" class="fabric-action-dialog erp-dialog--lg work-order-secondary-qty-dialog" @update:visible="close">
		<div class="work-order-secondary-qty">
			<Message severity="secondary" :closable="false">Enter the secondary quantity for each row. It can be changed at any time, also after the Work Order is submitted; nothing else on the rows changes.</Message>
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<Skeleton v-if="loading" height="160px" />
			<template v-else>
				<section v-for="section in sections" :key="section.table" class="work-order-secondary-qty__section" :aria-label="section.label">
					<h3>{{ section.label }} <span>{{ section.rows.length }} {{ section.rows.length === 1 ? "row" : "rows" }}</span></h3>
					<p v-if="!section.rows.length" class="work-order-secondary-qty__empty">No rows.</p>
					<div v-else class="work-order-secondary-qty__wrap" role="region" tabindex="0" :aria-label="`${section.label} secondary quantities`">
						<table class="erp-data-table">
							<thead><tr><th>Item</th><th class="erp-number">Quantity</th><th class="erp-number">Secondary qty</th></tr></thead>
							<tbody>
								<tr v-for="row in section.rows" :key="row.name">
									<td><strong>{{ row.item_variant }}</strong></td>
									<td class="erp-number">{{ quantity(row.qty) }} <small>{{ row.uom }}</small></td>
									<td class="work-order-secondary-qty__input">
										<div v-if="row.secondary_uom"><InputNumber v-model="row.secondary_qty" :aria-label="`Secondary qty in ${row.secondary_uom} for ${row.item_variant}`" :min="0" :max-fraction-digits="3" :disabled="busy" fluid /><span>{{ row.secondary_uom }}</span></div>
										<span v-else class="work-order-secondary-qty__none">No secondary UOM on this item</span>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</section>
			</template>
		</div>
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="busy" @click="close(false)" />
			<Button label="Save Secondary Qty" icon="pi pi-check" :loading="busy" :disabled="loading || !editableRows.length" @click="save" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, ref, watch } from "vue"

import { executeWorkOrderCommand } from "../../api/fabricStore.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	workOrder: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:visible", "changed"])

const rows = ref([])
const loading = ref(false)
const busy = ref(false)
const error = ref("")
const sections = computed(() => [
	{ table: "deliverables", label: "Deliverables", rows: rows.value.filter((row) => row.table === "deliverables") },
	{ table: "receivables", label: "Receivables", rows: rows.value.filter((row) => row.table === "receivables") },
])
const editableRows = computed(() => rows.value.filter((row) => row.secondary_uom))

watch(() => props.visible, (visible) => { if (visible) load() })

async function load() {
	rows.value = []
	error.value = ""
	loading.value = true
	try {
		const result = await executeWorkOrderCommand(props.workOrder.name, "get_secondary_quantities") || {}
		rows.value = (result.rows || []).map((row) => ({ ...row, secondary_qty: Number(row.secondary_qty) || null }))
	}
	catch (failure) { error.value = failure?.message || "Unable to load the secondary quantities." }
	finally { loading.value = false }
}

async function save() {
	busy.value = true
	error.value = ""
	const quantities = Object.fromEntries(editableRows.value.map((row) => [row.name, Number(row.secondary_qty) || 0]))
	try {
		const result = await executeWorkOrderCommand(props.workOrder.name, "update_secondary_quantities", { quantities }, props.workOrder.modified)
		emit("changed", result)
		emit("update:visible", false)
	}
	catch (failure) { error.value = failure?.message || "Unable to save the secondary quantities." }
	finally { busy.value = false }
}

function close(visible) { if (!busy.value) emit("update:visible", Boolean(visible)) }

function quantity(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }
</script>

<style scoped>
.work-order-secondary-qty { display: grid; gap: var(--erp-space-3); }
.work-order-secondary-qty__section { display: grid; gap: 6px; }
.work-order-secondary-qty__section h3 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: var(--erp-font-size-section); }
.work-order-secondary-qty__section h3 span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 700; }
.work-order-secondary-qty__empty { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.work-order-secondary-qty__wrap { max-width: 100%; max-height: 40vh; overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.work-order-secondary-qty__wrap:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }
.work-order-secondary-qty table { width: 100%; min-width: 560px; }
.work-order-secondary-qty td small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.work-order-secondary-qty__input { width: 220px; }
.work-order-secondary-qty__input > div { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 8px; }
.work-order-secondary-qty__input :deep(.p-inputnumber-input) { height: 32px; padding: 5px 8px; text-align: right; }
.work-order-secondary-qty__input span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 700; }
.work-order-secondary-qty__none { display: block; text-align: right; }
</style>
