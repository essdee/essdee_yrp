<template>
	<div class="ta-suppliers">
		<span v-for="chip in chips || []" :key="chip.supplier" v-tooltip.top="{ value: supplierChipTitle(chip), class: 'ta-supplier-tooltip' }" class="ta-supplier" :class="`ta-supplier--${supplierChipTone(chip)}`" tabindex="0" :aria-label="supplierChipTitle(chip)">{{ chip.supplier_name || chip.supplier }}</span>
		<span v-if="!chips?.length && !editable" class="ta-subtle">—</span>
		<Button v-if="editable" icon="pi pi-pencil" text rounded size="small" severity="secondary" :aria-label="`Planned Suppliers of ${action}`" title="Planned Suppliers" @click="emit('edit')" />
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Tooltip from "primevue/tooltip"

import { supplierChipTitle, supplierChipTone } from "./supplierChips.js"

/** Supplier chips of one T&A action: solid = planned with work, hollow = planned without work, amber = not planned. */
defineProps({
	action: { type: String, required: true },
	chips: { type: Array, default: () => [] },
	editable: { type: Boolean, default: false },
})
const emit = defineEmits(["edit"])
const vTooltip = Tooltip
</script>

<style scoped>
.ta-suppliers { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.ta-supplier { max-width: 160px; overflow: hidden; padding: 1px 8px; font-size: 12px; line-height: 18px; white-space: nowrap; text-overflow: ellipsis; border: 1px solid transparent; border-radius: 999px; cursor: default; }
.ta-supplier--planned { color: var(--erp-on-accent); background: var(--erp-accent); }
.ta-supplier--hollow { color: var(--erp-text-muted); background: transparent; border-color: var(--erp-border-strong); border-style: dashed; }
.ta-supplier--unplanned { color: var(--erp-attention-text); background: var(--erp-warning-soft); border-color: var(--erp-attention-border); }
</style>

<style>
.ta-supplier-tooltip { max-width: 360px; white-space: pre-line; }
</style>
