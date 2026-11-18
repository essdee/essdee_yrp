<template>
	<Dialog :visible="visible" modal :header="`Select ${documentLabel}`" class="erp-dialog--sm" @update:visible="emit('update:visible', $event)">
		<p class="lot-plan-picker__hint">This Lot has {{ options.length }} {{ documentLabel }}s. Choose one to open its {{ tabLabel }}.</p>
		<div class="lot-plan-picker__list" role="list">
			<button v-for="option in options" :key="option.name" type="button" class="lot-plan-picker__option" role="listitem" @click="emit('pick', option.name)">
				<strong>{{ option.name }}</strong>
				<span>{{ option.date }}</span>
				<span v-if="option.status" class="lot-plan-picker__status">{{ option.status }}</span>
			</button>
		</div>
	</Dialog>
</template>

<script setup>
import Dialog from "primevue/dialog"

defineProps({
	visible: { type: Boolean, default: false },
	documentLabel: { type: String, default: "" },
	tabLabel: { type: String, default: "" },
	options: { type: Array, default: () => [] },
})
const emit = defineEmits(["update:visible", "pick"])
</script>

<style scoped>
.lot-plan-picker__hint {
	margin: 0 0 10px;
	color: var(--erp-text-muted);
}

.lot-plan-picker__list {
	display: grid;
	gap: 6px;
}

.lot-plan-picker__option {
	display: grid;
	grid-template-columns: minmax(0, 1fr) auto auto;
	align-items: center;
	gap: 12px;
	padding: 10px 12px;
	color: var(--erp-text);
	text-align: left;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	cursor: pointer;
	font: inherit;
}

.lot-plan-picker__option:hover,
.lot-plan-picker__option:focus-visible {
	background: var(--erp-accent-soft);
	border-color: var(--erp-accent-border);
}

.lot-plan-picker__option span {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
	font-variant-numeric: tabular-nums;
}

.lot-plan-picker__status {
	padding: 1px 8px;
	background: var(--erp-surface-muted);
	border-radius: var(--erp-pill-radius);
}
</style>
