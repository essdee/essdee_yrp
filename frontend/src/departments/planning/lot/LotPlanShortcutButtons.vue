<template>
	<span v-if="shortcuts.length" class="lot-plan-shortcuts" :class="{ 'is-compact': compact }" @click.stop>
		<Button
			v-for="shortcut in shortcuts"
			:key="shortcut.key"
			:label="shortcut.label"
			:icon="compact ? undefined : 'pi pi-table'"
			:size="compact ? 'small' : undefined"
			:aria-label="`Open ${shortcut.label} of Lot ${lot}`"
			severity="secondary"
			outlined
			:loading="busy === shortcut.key"
			:disabled="disabled || Boolean(busy)"
			:data-plan-shortcut="shortcut.key"
			@click="open(shortcut)"
		/>
		<LotPlanPickerDialog
			v-model:visible="picker.visible"
			:document-label="picker.shortcut?.documentLabel"
			:tab-label="picker.shortcut?.label"
			:options="picker.options"
			@pick="pick"
		/>
	</span>
</template>

<script setup>
import Button from "primevue/button"
import { useToast } from "primevue/usetoast"
import { computed, reactive, ref } from "vue"
import { useRouter } from "vue-router"

import { getLotCuttingPlans, getLotFinishingPlans } from "../../../api/planning.js"
import LotPlanPickerDialog from "./LotPlanPickerDialog.vue"
import { noPlanMessage, planOptions, planRoute, resolvePlanTarget, visiblePlanShortcuts } from "./lotPlanShortcuts.js"

/** CCR / OCR buttons for one lot: one plan opens its tab, several open a picker, none warns. */
const props = defineProps({
	lot: { type: String, required: true },
	access: { type: Object, default: () => ({}) },
	disabled: Boolean,
	compact: Boolean,
})
const router = useRouter()
const toast = useToast()
const busy = ref("")
const picker = reactive({ visible: false, shortcut: null, options: [] })
const planLoaders = { ccr: getLotCuttingPlans, ocr: getLotFinishingPlans }
const shortcuts = computed(() => visiblePlanShortcuts(props.access))

async function open(shortcut) {
	const lot = props.lot
	busy.value = shortcut.key
	try {
		const plans = await planLoaders[shortcut.key](lot)
		if (lot !== props.lot) return
		const target = resolvePlanTarget(plans)
		if (target.kind === "none") toast.add({ severity: "warn", summary: noPlanMessage(shortcut, lot), life: 5000 })
		else if (target.kind === "open") router.push(planRoute(shortcut, target.name))
		else Object.assign(picker, { visible: true, shortcut, options: planOptions(shortcut, plans) })
	} catch (reason) {
		toast.add({ severity: "error", summary: `Unable to load ${shortcut.documentLabel}s`, detail: reason?.message, life: 5000 })
	} finally {
		busy.value = ""
	}
}

function pick(name) {
	picker.visible = false
	router.push(planRoute(picker.shortcut, name))
}
</script>

<style scoped>
.lot-plan-shortcuts {
	display: inline-flex;
	align-items: center;
	gap: 8px;
}

.lot-plan-shortcuts.is-compact {
	gap: 4px;
}

.lot-plan-shortcuts.is-compact :deep(.p-button) {
	padding: 1px 7px;
	font-size: 11px;
}
</style>
