<template>
	<Dialog :visible="visible" modal :dismissable-mask="false" header="Recalculate Deliverables" class="fabric-action-dialog erp-dialog--lg work-order-recalculate-dialog" @update:visible="close">
		<div class="work-order-recalculate">
			<Message v-if="!applied" severity="secondary" :closable="false">Accessory deliverables of {{ workOrder.name }} are rebuilt from the current Item Production Detail. Delivered items stay unchanged. Sewing Plan and Quality Inspection entries are not affected.</Message>
			<Message v-else severity="success" :closable="false">{{ appliedMessage }}</Message>
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<Skeleton v-if="loading" height="160px" />
			<template v-else-if="rows.length">
				<p v-if="!applied" class="work-order-recalculate__summary" role="status">{{ summary }}</p>
				<div class="work-order-recalculate__wrap" role="region" tabindex="0" aria-label="Recalculated deliverables">
					<table class="erp-data-table">
						<thead><tr><th>Item</th><th class="erp-number">Current qty</th><th class="erp-number">Recalculated qty</th><th>Result</th></tr></thead>
						<tbody>
							<tr v-for="row in rows" :key="`${row.kind}-${row.row_name || ''}-${row.item_variant}`" :class="`work-order-recalculate__row--${row.kind}`">
								<td><strong>{{ row.item_variant }}</strong></td>
								<td class="erp-number">{{ quantity(row.old_qty, row.uom) }}</td>
								<td class="erp-number">{{ quantity(row.new_qty, row.uom) }}</td>
								<td><span class="work-order-recalculate__status">{{ LABELS[row.kind] }}</span><small v-if="row.reason">{{ row.reason }}</small></td>
							</tr>
						</tbody>
					</table>
				</div>
			</template>
			<p v-else-if="!error" class="work-order-recalculate__summary">This Work Order has no accessory deliverables to recalculate.</p>
		</div>
		<template #footer>
			<Button :label="applied ? 'Done' : 'Cancel'" severity="secondary" text :disabled="busy" @click="close(false)" />
			<Button v-if="!applied" label="Recalculate" icon="pi pi-refresh" :loading="busy" :disabled="loading || !plan.has_changes" @click="apply" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, ref, watch } from "vue"

import { callMethod } from "../../api/frappe.js"

const METHOD = "essdee_yrp.work_order_recalculate"
const KINDS = ["added", "updated", "removed", "kept", "unchanged"]
const LABELS = { added: "Added", updated: "Updated", removed: "Removed", kept: "Kept (delivered)", unchanged: "No change" }

const props = defineProps({
	visible: { type: Boolean, default: false },
	workOrder: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:visible", "changed"])

const plan = ref({})
const loading = ref(false)
const busy = ref(false)
const applied = ref(false)
const error = ref("")
const rows = computed(() => KINDS.flatMap((kind) => (plan.value[kind] || []).map((row) => ({ ...row, kind }))))
const counts = computed(() => Object.fromEntries(KINDS.map((kind) => [kind, (plan.value[kind] || []).length])))
const summary = computed(() => {
	const { added, updated, removed, kept } = counts.value
	if (!plan.value.has_changes) return `Deliverables already match the Item Production Detail.${kept ? ` ${kept} delivered row(s) kept.` : ""}`
	return `${added} to add, ${updated} to update, ${removed} to remove, ${kept} delivered row(s) kept.`
})
const appliedMessage = computed(() => {
	const { added, updated, removed } = counts.value
	return `Deliverables recalculated: ${added} added, ${updated} updated, ${removed} removed.`
})

watch(() => props.visible, (visible) => { if (visible) load() })

async function load() {
	plan.value = {}
	applied.value = false
	error.value = ""
	loading.value = true
	try { plan.value = await callMethod(`${METHOD}.get_recalculate_deliverables_preview`, { work_order: props.workOrder.name }) || {} }
	catch (failure) { error.value = failure?.message || "Unable to recalculate the deliverables." }
	finally { loading.value = false }
}

async function apply() {
	busy.value = true
	error.value = ""
	try {
		plan.value = await callMethod(`${METHOD}.apply_recalculate_deliverables`, {
			work_order: props.workOrder.name,
			modified: props.workOrder.modified,
		}) || {}
		applied.value = true
		emit("changed")
	}
	catch (failure) { error.value = failure?.message || "Unable to update the deliverables." }
	finally { busy.value = false }
}

function close(visible) { if (!busy.value) emit("update:visible", Boolean(visible)) }

function quantity(value, uom) {
	if (value === null || value === undefined) return "—"
	return `${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 3 })} ${uom || ""}`
}
</script>

<style scoped>
.work-order-recalculate { display: grid; gap: var(--erp-space-3); }
.work-order-recalculate__summary { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.work-order-recalculate__wrap { max-width: 100%; max-height: 52vh; overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.work-order-recalculate__wrap:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }
.work-order-recalculate table { width: 100%; min-width: 640px; }
.work-order-recalculate td small { display: block; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.work-order-recalculate__status { font-weight: 700; }
.work-order-recalculate__row--added .work-order-recalculate__status, .work-order-recalculate__row--updated .work-order-recalculate__status { color: var(--erp-success-text); }
.work-order-recalculate__row--removed .work-order-recalculate__status { color: var(--erp-danger); }
.work-order-recalculate__row--unchanged { color: var(--erp-text-muted); }
</style>
