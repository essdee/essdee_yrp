<template>
	<div class="lvt-table-frame">
		<table class="lvt-inputs">
			<thead>
				<tr>
					<th>What went into 1 {{ row.unit }} of this item</th>
					<th>From process · GRN</th>
					<th class="lvt-num">Qty per {{ row.unit }}</th>
					<th class="lvt-num">Its rate out there</th>
					<th class="lvt-num">₹ per {{ row.unit }}</th>
				</tr>
			</thead>
			<tbody>
				<template v-for="line in row.inputs" :key="`${line.item}:${line.voucher}`">
					<tr>
						<td>{{ line.item }}<span v-if="line.sources" class="lvt-muted"> (from {{ line.sources.length }} line{{ line.sources.length === 1 ? "" : "s" }}, share per {{ row.unit }} below)</span></td>
						<td>{{ line.stage }} · <DocumentLink class="lvt-mono" :doctype="line.voucher_type" :name="line.voucher" :label="shortDoc(line.voucher)" /></td>
						<td class="lvt-num">{{ formatPerUnitQty(line.qty, line.unit) }}</td>
						<td class="lvt-num">{{ formatMoney(line.rate) }}/{{ line.unit }}</td>
						<td class="lvt-num">{{ formatMoney(line.amount) }}</td>
					</tr>
					<tr v-for="source in line.sources || []" :key="`${line.item}:${source.item}:${source.voucher}`" class="lvt-inputs__source">
						<td>↳ {{ source.item }}</td>
						<td>{{ source.stage }} · <DocumentLink class="lvt-mono" :doctype="source.voucher_type" :name="source.voucher" :label="shortDoc(source.voucher)" /></td>
						<td class="lvt-num">{{ formatPerUnitQty(source.qty, source.unit) }}</td>
						<td class="lvt-num">{{ formatMoney(source.rate) }}/{{ source.unit }}</td>
						<td class="lvt-num">{{ formatMoney(source.amount) }}</td>
					</tr>
				</template>
				<tr v-if="!row.inputs.length">
					<td colspan="4">{{ row.residual ? `${row.residual}: no traceable origin; rate as held on` : "Purchased / received, no earlier process. Rate on" }} {{ shortDoc(row.voucher) }}</td>
					<td class="lvt-num">{{ formatMoney(row.purchase_rate) }}</td>
				</tr>
				<tr v-if="row.inputs.length" class="lvt-inputs__sum">
					<td colspan="4">= Rate in</td>
					<td class="lvt-num">{{ formatMoney(row.rate_in) }}</td>
				</tr>
				<tr v-for="line in row.accessory_inputs" :key="`acc:${line.item}:${line.voucher}`">
					<td>{{ line.item }} <span class="lvt-muted">(accessory)</span></td>
					<td>{{ line.stage }} · <DocumentLink class="lvt-mono" :doctype="line.voucher_type" :name="line.voucher" :label="shortDoc(line.voucher)" /></td>
					<td class="lvt-num">{{ formatPerUnitQty(line.qty, line.unit) }}</td>
					<td class="lvt-num">{{ formatMoney(line.rate) }}/{{ line.unit }}</td>
					<td class="lvt-num">{{ formatMoney(line.amount) }}</td>
				</tr>
				<tr v-if="row.accessory_inputs.length" class="lvt-inputs__sum">
					<td colspan="4">= + Accessories</td>
					<td class="lvt-num">{{ formatMoney(row.accessories) }}</td>
				</tr>
			</tbody>
		</table>
	</div>
</template>

<script setup>
import DocumentLink from "../../../../components/common/DocumentLink.vue"
import { formatMoney, formatPerUnitQty, shortDoc } from "./lotValuation.js"

defineProps({ row: { type: Object, required: true } })
</script>
