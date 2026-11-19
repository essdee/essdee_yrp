<template>
	<p v-if="!weight.rows.length" class="ipd-approval__empty">No weights entered.</p>
	<table v-else class="erp-data-table ipd-approval__table ipd-approval__weight">
		<thead>
			<tr>
				<th v-for="column in weight.columns" :key="column" scope="col">{{ column }}</th>
				<th scope="col">Dia</th>
				<th scope="col" class="is-number">Weight</th>
			</tr>
		</thead>
		<tbody>
			<tr v-for="(row, index) in rows" :key="index" :class="{ 'is-group': row.startsGroup && index > 0, 'is-outlier': row.outlier_median }">
				<td v-for="key in Object.keys(row.values)" :key="key"><strong v-if="key in row.shown">{{ row.shown[key] }}</strong></td>
				<td v-if="weight.colour_attribute">
					<div class="ipd-approval__chips"><span v-for="colour in row.colourChips" :key="colour" class="ipd-approval__chip">{{ colour }}</span></div>
				</td>
				<td v-if="weight.size_attribute">{{ row.size_label }}</td>
				<td class="ipd-approval__subtle">{{ row.dia }}</td>
				<td class="is-number">
					<strong>{{ grams(row.weight) }}</strong> <span class="ipd-approval__subtle">({{ +Number(row.weight || 0).toFixed(4) }} kg)</span>
					<div v-if="row.outlier_median" class="ipd-approval__outlier"><i class="pi pi-exclamation-triangle" aria-hidden="true" /> vs ~{{ grams(row.outlier_median) }} for the other colours</div>
				</td>
			</tr>
		</tbody>
	</table>
	<p class="ipd-approval__legend">
		Exactly as entered in the IPD cutting grid<template v-if="weight.from_panel_matrix"> · Stored grid generated from the panel-wise matrix</template>. Identical neighbouring sizes and colours are merged. No totals.
	</p>
</template>

<script setup>
import { computed } from "vue"

import { grams, weightRows } from "./ipdApproval.js"

const props = defineProps({
	weight: { type: Object, required: true },
	colours: { type: Array, default: () => [] },
})
const rows = computed(() => weightRows(props.weight, props.colours))
</script>
