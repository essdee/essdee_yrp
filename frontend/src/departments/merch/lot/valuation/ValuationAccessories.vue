<template>
	<p class="lvt-subhead">Accessories used in {{ section.title }}</p>
	<div class="lvt-table-frame">
		<table class="lvt-accessories">
			<thead>
				<tr>
					<th>Accessory</th>
					<th>GRN · PO</th>
					<th class="lvt-num">Qty per {{ unit }}</th>
					<th class="lvt-num">Rate</th>
					<th class="lvt-num lvt-rates__add lvt-k-pi">+ PI adjustment</th>
					<th class="lvt-num">= Rate</th>
					<th class="lvt-num">₹ added per {{ unit }}</th>
					<th class="lvt-num">Qty used</th>
					<th class="lvt-num">Total ₹</th>
				</tr>
			</thead>
			<tbody>
				<tr v-for="accessory in section.accessories" :key="`${accessory.item}:${accessory.voucher}`">
					<td class="lvt-rates__item">{{ accessory.item }}</td>
					<td class="lvt-mono">
						<DocumentLink :doctype="accessory.voucher_type" :name="accessory.voucher" :label="shortDoc(accessory.voucher)" />
						<template v-if="accessory.against_id"> · <DocumentLink :doctype="poDoctype" :name="accessory.against_id" :label="shortDoc(accessory.against_id)" /></template>
					</td>
					<td class="lvt-num">{{ formatPerUnitQty(accessory.per_unit) }}</td>
					<td class="lvt-num">{{ formatMoney(accessory.rate) }}</td>
					<td class="lvt-num" :class="{ 'lvt-zero': isZero(accessory.pi) }" :tabindex="isZero(accessory.pi) ? undefined : 0" v-on="isZero(accessory.pi) ? {} : hoverHandlers(hover, () => accessoryHover('pi', accessory, unit))">{{ formatAdd(accessory.pi) }}</td>
					<td class="lvt-num">{{ formatMoney(accessory.rate + accessory.pi) }}</td>
					<td class="lvt-num" tabindex="0" v-on="hoverHandlers(hover, () => accessoryHover('added', accessory, unit))">{{ formatMoney(accessory.added_per_unit) }}</td>
					<td class="lvt-num">{{ formatPerUnitQty(accessory.qty) }}</td>
					<td class="lvt-num" tabindex="0" v-on="hoverHandlers(hover, () => accessoryHover('total', accessory, unit))">{{ formatMoney(accessory.total) }}</td>
				</tr>
			</tbody>
			<tfoot>
				<tr>
					<td colspan="6">{{ footer.label }}</td>
					<td class="lvt-num">{{ footer.value === null ? "" : formatMoney(footer.value) }}</td>
					<td />
					<td class="lvt-num">{{ formatMoney(total) }}</td>
				</tr>
			</tfoot>
		</table>
	</div>
</template>

<script setup>
import { computed, inject } from "vue"

import DocumentLink from "../../../../components/common/DocumentLink.vue"
import { formatAdd, formatMoney, formatPerUnitQty, isZero, shortDoc } from "./lotValuation.js"
import { accessoryHover } from "./valuationHoverContent.js"
import { hoverHandlers } from "./valuationHover.js"

const props = defineProps({ section: { type: Object, required: true } })
const hover = inject("valuationHover")
const poDoctype = "YRP Purchase Order"
const unit = computed(() => props.section.rows[0]?.unit || "unit")
const total = computed(() => props.section.accessories.reduce((sum, accessory) => sum + accessory.total, 0))
const footer = computed(() => {
	const first = props.section.rows[0]?.accessories || 0
	const sum = props.section.accessories.reduce((value, accessory) => value + accessory.added_per_unit, 0)
	if (!props.section.rows.every((row) => Math.abs(row.accessories - first) < 0.005)) return { label: `+ Accessories per ${unit.value} differs by item (see ▸ on each row)`, value: null }
	if (Math.abs(sum - first) < 0.005) return { label: `Sum per ${unit.value}, same for every item = + Accessories per ${unit.value}`, value: first }
	return { label: `Each item takes only the accessories listed under its ▸, so + Accessories per ${unit.value} =`, value: first }
})
</script>
