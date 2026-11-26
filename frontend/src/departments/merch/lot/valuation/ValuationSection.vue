<template>
	<section class="lvt-panel lvt-stage" :aria-label="section.title">
		<header class="lvt-stage__head">
			<span class="lvt-stage__num">{{ index }}</span>
			<h3>{{ section.title }}</h3>
			<span v-if="section.who" class="lvt-muted">{{ section.who }}</span>
		</header>
		<div v-if="section.docs.length" class="lvt-docs">
			<span v-for="doc in section.docs" :key="`${doc.label}:${doc.name}`" class="lvt-doc" v-on="hoverHandlers(hover, () => documentHover(doc))">
				<em>{{ doc.label }}</em><DocumentLink :doctype="doc.doctype" :name="doc.name" :label="shortDoc(doc.name)" />
			</span>
		</div>
		<p v-for="note in section.notes" :key="note" class="lvt-note">{{ note }}</p>
		<div class="lvt-table-frame">
			<table class="lvt-rates">
				<thead>
					<tr>
						<th aria-label="Expand" />
						<th>Item</th>
						<th>GRN</th>
						<th class="lvt-num">Qty</th>
						<th>UOM</th>
						<th class="lvt-num">Rate in</th>
						<th v-for="column in columns" :key="column.key" class="lvt-num lvt-rates__add" :class="`lvt-k-${column.key}`">{{ column.label }}</th>
						<th class="lvt-num">= Rate out</th>
						<th class="lvt-num">Total ₹</th>
					</tr>
				</thead>
				<tbody>
					<template v-for="(row, rowIndex) in section.rows" :key="`${row.item}:${row.voucher}`">
						<tr>
							<td>
								<button type="button" class="lvt-toggle" :aria-expanded="opened.has(rowIndex)" aria-label="Show what went into one unit" @click="toggle(rowIndex)">{{ opened.has(rowIndex) ? "▾" : "▸" }}</button>
							</td>
							<td class="lvt-rates__item">
								{{ itemLabel(row, section) }}
								<span v-for="tag in itemTags(row)" :key="tag.label" class="lvt-tag" :class="`lvt-tag--${tag.tone}`">{{ tag.label }}</span>
							</td>
							<td class="lvt-mono" v-on="hoverHandlers(hover, () => documentHover({ name: row.voucher, doctype: row.voucher_type }))">
								<DocumentLink :doctype="row.voucher_type" :name="row.voucher" :label="shortDoc(row.voucher)" />
							</td>
							<td class="lvt-num">{{ formatQty(row.qty) }}</td>
							<td>{{ row.uom_label }}</td>
							<td class="lvt-num" tabindex="0" v-on="hoverHandlers(hover, () => rateInHover(row))">{{ formatMoney(row.rate_in) }}</td>
							<td
								v-for="column in columns"
								:key="column.key"
								class="lvt-num"
								:class="{ 'lvt-zero': isZero(row[column.key]), 'lvt-negative': row[column.key] < -0.005 }"
								:tabindex="isZero(row[column.key]) ? undefined : 0"
								v-on="isZero(row[column.key]) ? {} : hoverHandlers(hover, () => addHover(column, row, section))"
							>{{ formatAdd(row[column.key]) }}</td>
							<td class="lvt-num lvt-rates__out" tabindex="0" v-on="hoverHandlers(hover, () => rateOutHover(row, columns))">{{ formatMoney(row.rate_out) }}</td>
							<td class="lvt-num" tabindex="0" v-on="hoverHandlers(hover, () => totalHover(row))">{{ formatMoney(row.total) }}</td>
						</tr>
						<tr v-if="opened.has(rowIndex)" class="lvt-rates__inputs">
							<td />
							<td :colspan="columns.length + 7"><ValuationInputs :row="row" /></td>
						</tr>
					</template>
				</tbody>
				<tfoot>
					<tr>
						<td />
						<td :colspan="columns.length + 6">Total of {{ section.title }}</td>
						<td class="lvt-num">{{ formatMoney(section.total) }}</td>
					</tr>
				</tfoot>
			</table>
		</div>
		<p v-if="section.pieces_per_box" class="lvt-per-piece">
			<span v-for="row in section.rows" :key="`${row.item}:${row.voucher}`">{{ row.item }}: = <b>{{ formatMoney(row.rate_out_piece) }}</b> per piece ({{ formatMoney(row.rate_out) }} ÷ {{ formatQty(row.pieces_per_box) }})</span>
		</p>
		<ValuationAccessories v-if="section.accessories.length" :section="section" />
	</section>
</template>

<script setup>
import { inject, reactive } from "vue"

import DocumentLink from "../../../../components/common/DocumentLink.vue"
import { formatAdd, formatMoney, formatQty, isZero, itemLabel, itemTags, shortDoc } from "./lotValuation.js"
import { addHover, documentHover, rateInHover, rateOutHover, totalHover } from "./valuationHoverContent.js"
import { hoverHandlers } from "./valuationHover.js"
import ValuationAccessories from "./ValuationAccessories.vue"
import ValuationInputs from "./ValuationInputs.vue"

defineProps({
	section: { type: Object, required: true },
	index: { type: Number, required: true },
	columns: { type: Array, required: true },
})
const hover = inject("valuationHover")
const opened = reactive(new Set())

function toggle(rowIndex) {
	hover.hide()
	if (opened.has(rowIndex)) opened.delete(rowIndex)
	else opened.add(rowIndex)
}
</script>
