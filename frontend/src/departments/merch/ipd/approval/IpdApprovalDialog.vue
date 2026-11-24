<template>
	<Dialog :visible="visible" modal class="erp-entity-dialog erp-dialog--xl ipd-approval" :closable="!busy" :dismissable-mask="false" @update:visible="close">
		<template #header>
			<div class="ipd-approval__title">
				<h2>Review before approving</h2>
				<p v-if="header"><strong>{{ header.name }}</strong> · {{ headerMeta }}</p>
			</div>
			<Tag v-if="header" :value="header.status" :severity="header.status === 'Approved' ? 'success' : 'warn'" class="ipd-approval__status" />
		</template>
		<div v-if="loading" class="ipd-approval__state"><i class="pi pi-spin pi-spinner" aria-hidden="true" /><span>Loading the IPD summary…</span></div>
		<Message v-else-if="error" severity="error" :closable="false">{{ error }}</Message>
		<div v-else-if="summary" class="erp-dialog-body ipd-approval__body">
			<div class="ipd-approval__stats">
				<div v-for="stat in stats" :key="stat.label" class="ipd-approval__stat">
					<span class="ipd-approval__stat-label">{{ stat.label }}</span>
					<span class="ipd-approval__stat-value">{{ stat.value }}</span>
					<span v-if="stat.note" class="ipd-approval__stat-note">{{ stat.note }}</span>
				</div>
			</div>
			<div v-if="summary.warnings.length" class="ipd-approval__issues" :class="{ 'is-danger': hasDanger }">
				<strong>{{ summary.warnings.length }} {{ summary.warnings.length === 1 ? "warning" : "warnings" }} to check</strong>
				<IpdApprovalAlerts :warnings="summary.warnings" />
				<label class="ipd-approval__ack">
					<Checkbox v-model="acknowledged" binary input-id="ipd-approval-ack" :disabled="busy" />
					<span>I have checked the warnings</span>
				</label>
			</div>
			<Message v-else severity="success" size="small" :closable="false">No warnings in this IPD.</Message>
			<IpdApprovalWorkOrders v-if="summary.work_orders" :work-orders="summary.work_orders" />
			<div class="ipd-approval__grid">
				<IpdApprovalSection
					v-for="(section, index) in sections"
					:key="section.key"
					:number="index + 1"
					:section="section"
					:warnings="summary.warnings"
					:attributes="summary.attributes"
				/>
			</div>
		</div>
		<template #footer>
			<span class="ipd-approval__hint">{{ hint }}</span>
			<Button label="Cancel" severity="secondary" text :disabled="busy" @click="close(false)" />
			<Button label="Approve" icon="pi pi-check" :loading="busy" :disabled="!summary || !gate.canApprove" @click="confirm" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Tag from "primevue/tag"
import { computed, ref, watch } from "vue"

import { getIpdApprovalSummary } from "../../../../api/merch.js"
import { formatDisplayDate } from "../../../../utils/dateFormat.js"
import IpdApprovalAlerts from "./IpdApprovalAlerts.vue"
import IpdApprovalSection from "./IpdApprovalSection.vue"
import IpdApprovalWorkOrders from "./IpdApprovalWorkOrders.vue"
import { approvalGate, orderedSections, sizeRange, weightSpan } from "./ipdApproval.js"
import "./approval.css"

const props = defineProps({
	visible: { type: Boolean, default: false },
	name: { type: String, default: "" },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible", "confirm"])
const summary = ref(null)
const loading = ref(false)
const error = ref("")
const acknowledged = ref(false)
let loadSequence = 0

const header = computed(() => summary.value?.header || null)
const sections = computed(() => orderedSections(summary.value?.sections))
const hasDanger = computed(() => summary.value?.warnings.some((warning) => warning.level === "danger"))
const gate = computed(() => approvalGate(summary.value?.warnings, acknowledged.value, props.busy))
const hint = computed(() => gate.value.needsAcknowledgement && !acknowledged.value
	? "Tick “I have checked the warnings” to enable Approve."
	: "Approved IPDs become read only. Changes need a new version.")
const headerMeta = computed(() => {
	const value = header.value
	const lots = value.lots.length ? ` · Used by ${value.lots.length === 1 ? "lot" : "lots"} ${value.lots.join(", ")}` : " · Not used by any lot yet"
	return `v${value.version} · Created by ${value.created_by} on ${formatDisplayDate(value.created_on)} · Modified by ${value.modified_by} on ${formatDisplayDate(value.modified_on)}${lots}`
})
const stats = computed(() => {
	const { attributes, key_numbers: numbers } = summary.value
	return [
		{ label: "Item", value: header.value.item, note: header.value.item_group || "" },
		{ label: "Version", value: `v${header.value.version}` },
		{ label: attributes.primary || "Size", value: sizeRange(attributes.sizes) || "—", note: `${attributes.sizes.length} sizes` },
		{ label: "Colours", value: numbers.colours, note: attributes.is_set_item ? `Set: ${attributes.set_parts.join(" + ")}` : "" },
		{ label: "Panels", value: numbers.panels, note: `${numbers.pieces} pieces` },
		{ label: "Piece weight", value: weightSpan(numbers.piece_weight), note: numbers.panel_wise ? "panel-wise" : "" },
	]
})

async function load() {
	const sequence = ++loadSequence
	summary.value = null
	acknowledged.value = false
	error.value = ""
	loading.value = true
	try {
		const result = await getIpdApprovalSummary(props.name)
		if (sequence === loadSequence) summary.value = result
	} catch (reason) {
		if (sequence === loadSequence) error.value = reason?.message || "Unable to load the IPD summary."
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}
function close(value) {
	if (!value && !props.busy) emit("update:visible", false)
}
function confirm() {
	if (summary.value && gate.value.canApprove) emit("confirm")
}

watch(() => props.visible, (visible) => { if (visible && props.name) load() }, { immediate: true })
</script>
