<template>
	<section class="lvt-panel lvt-summary" aria-label="Value summary">
		<div class="lvt-summary__left">
			<template v-if="boxes">
				<span class="lvt-eyebrow">Packed output · valued per box</span>
				<strong class="lvt-big"><span class="lvt-nowrap">{{ formatQty(boxes.boxes) }} boxes</span> <span class="lvt-nowrap">· {{ formatMoney(summary.ledger_value) }}</span></strong>
				<dl class="lvt-kv">
					<template v-for="size in boxes.sizes" :key="size.item">
						<dt>{{ size.item }}</dt><dd>{{ formatQty(size.boxes) }} × <b>{{ formatMoney(size.rate) }}</b> per box</dd>
					</template>
					<dt>Average per piece</dt><dd>{{ formatMoney(perUnit) }} <span class="lvt-muted">({{ formatMoney(summary.ledger_value) }} ÷ {{ formatQty(summary.qty) }} pcs)</span></dd>
				</dl>
			</template>
			<template v-else>
				<span class="lvt-eyebrow">Value per {{ unit }}</span>
				<strong class="lvt-big">{{ formatMoney(perUnit) }}</strong>
				<dl class="lvt-kv">
					<dt>{{ rootLabel }}</dt><dd>{{ formatQty(summary.qty, summary.uom) }}</dd>
					<dt>Total value</dt><dd>{{ formatMoney(summary.ledger_value) }}</dd>
				</dl>
			</template>
			<div class="lvt-stack" role="img" :aria-label="`Value by contribution type: ${stackLabel}`">
				<span
					v-for="category in positiveCategories"
					:key="category.key"
					:class="`lvt-k-${category.key}`"
					:style="{ width: `${(category.value / positiveTotal) * 100}%` }"
					v-on="hoverHandlers(hover, () => categoryHover(category, summary))"
				/>
			</div>
			<ul class="lvt-legend">
				<li
					v-for="category in categories"
					:key="category.key"
					:class="`lvt-k-${category.key}`"
					tabindex="0"
					v-on="hoverHandlers(hover, () => categoryHover(category, summary))"
				>
					<i class="lvt-swatch" />{{ category.label }} <b>{{ formatMoney(perUnitOf(category.value)) }}</b>
					<small>{{ formatPercent(category.value, summary.ledger_value) }}</small>
				</li>
			</ul>
		</div>
		<div class="lvt-summary__right">
			<span class="lvt-eyebrow">Where one {{ unit }}'s value came from (₹ per {{ unit }}, in flow order)</span>
			<div class="lvt-waterfall">
				<div
					v-for="item in waterfall.rows"
					:key="item.stage"
					class="lvt-waterfall__row"
					tabindex="0"
					v-on="hoverHandlers(hover, () => waterfallHover(item, summary))"
				>
					<span class="lvt-waterfall__label">{{ item.stage }}</span>
					<span class="lvt-waterfall__track"><i :class="`lvt-k-${item.category}`" :style="{ left: `${item.left}%`, width: `${Math.max(item.width, 0.4)}%` }" /></span>
					<span class="lvt-waterfall__value">{{ formatMoney(perUnitOf(item.value)) }}</span>
				</div>
				<div class="lvt-waterfall__row lvt-waterfall__row--total">
					<span class="lvt-waterfall__label">{{ capitalised }} value</span>
					<span class="lvt-waterfall__track"><i class="lvt-waterfall__total" /></span>
					<span class="lvt-waterfall__value">{{ formatMoney(perUnit) }}</span>
				</div>
			</div>
		</div>
	</section>
</template>

<script setup>
import { computed, inject } from "vue"

import { categoryRows, formatMoney, formatPercent, formatQty, waterfallRows } from "./lotValuation.js"
import { categoryHover, waterfallHover } from "./valuationHoverContent.js"
import { hoverHandlers } from "./valuationHover.js"

const props = defineProps({
	summary: { type: Object, required: true },
	rootLabel: { type: String, default: "Receipts" },
	boxes: { type: Object, default: null },
})
const hover = inject("valuationHover")
const unit = computed(() => (props.summary.uom || "unit").replace(/s$/, "").toLowerCase())
const capitalised = computed(() => unit.value.charAt(0).toUpperCase() + unit.value.slice(1))
const perUnit = computed(() => (props.summary.qty ? props.summary.ledger_value / props.summary.qty : 0))
const categories = computed(() => categoryRows(props.summary))
const positiveCategories = computed(() => categories.value.filter((category) => category.value > 0))
const positiveTotal = computed(() => positiveCategories.value.reduce((sum, category) => sum + category.value, 0) || 1)
const stackLabel = computed(() => categories.value.map((category) => `${category.label} ${formatPercent(category.value, props.summary.ledger_value)}`).join(", "))
const waterfall = computed(() => waterfallRows(props.summary))

function perUnitOf(value) {
	return props.summary.qty ? value / props.summary.qty : 0
}
</script>
