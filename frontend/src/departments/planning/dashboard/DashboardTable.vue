<template>
	<section class="pd-panel pd-section" aria-label="Lot-wise table">
		<header class="pd-toolbar">
			<div>
				<h2>{{ isGrouped ? "PPOs" : "Lots" }}</h2>
				<p :data-count="sorted.length">{{ rangeText }} · sorted by {{ sortLabel }}<template v-if="isGrouped"> · {{ plural(rows.length, "lot") }} grouped</template></p>
			</div>
			<div class="pd-toolbar__end">
				<label class="pd-check"><Checkbox v-model="isGrouped" binary input-id="pd-group-by-ppo" /><span>Group by PPO</span></label>
				<Button label="Copy CSV" size="small" severity="secondary" outlined @click="copy" />
			</div>
		</header>
		<div class="pd-table-wrap pd-table-wrap--scroll">
			<table class="pd-table pd-dash-table" :class="{ 'is-grouped': isGrouped }">
				<thead>
					<tr>
						<th class="pd-number">#</th>
						<th v-for="column in COLUMNS" :key="column.key" :class="{ 'pd-number': column.isNumber }" :title="columnTitle(column)" :aria-sort="ariaSort(column.key)">
							<button type="button" class="pd-sort" :data-sort="column.key" @click="sortBy(column.key)">{{ isGrouped && column.key === "lot" ? "Lots" : column.label }}<i>{{ sortMark(column.key) }}</i></button>
						</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, index) in shown.rows" :key="rowKey(row)" :class="{ 'is-dispatched': row.status === 'Dispatched', 'is-unlinked': isUnlinked(row) }" :data-row="rowKey(row)">
						<td class="pd-number pd-muted">{{ index + 1 }}</td>
						<td><button type="button" class="pd-link" @click="emit('drill', rowDrill(row, false))">{{ row.ppo }}</button></td>
						<td :class="isGrouped ? 'pd-lots-cell' : 'pd-lot-cell'">
							<template v-if="isGrouped">
								<template v-for="(lot, lotIndex) in linkedLots(row)" :key="lot.lot"><span v-if="lotIndex" class="pd-muted">, </span><button type="button" class="pd-link" @click="emit('drill', rowDrill(lot, true))">{{ lot.lot }}</button></template>
								<template v-if="!row.lotCount"><span class="pd-muted">—</span><small v-if="row.lots[0].delivery" class="pd-sub" data-unlinked-delivery>Delivery {{ formatDisplayDate(row.lots[0].delivery) }}</small></template>
							</template>
							<template v-else-if="!row.lot"><span class="pd-muted">—</span><small v-if="row.delivery" class="pd-sub" data-unlinked-delivery>Delivery {{ formatDisplayDate(row.delivery) }}</small></template>
							<button v-else type="button" class="pd-link pd-ellipsis" :title="row.lot" @click="emit('drill', rowDrill(row, true))">{{ row.lot }}</button>
						</td>
						<td class="pd-item-cell" :title="row.isGroup && row.items.length > 1 ? row.items.join(', ') : row.item">{{ row.item }}<small v-if="isUnlinked(row) && itemName(row) && itemName(row) !== row.item" class="pd-sub">{{ itemName(row) }}</small></td>
						<td class="pd-ellipsis-cell" :title="row.product_category || ''">{{ row.product_category || "" }}</td>
						<td>
							<span class="pd-status-mix" :title="row.isGroup ? row.breakdown : undefined"><LotStatusPill :status="row.status" /><LotStatusPill v-if="!row.isGroup && row.purchase_split" :status="row.purchase_split.status" :title="`${formatQuantity(row.purchase_split.pieces)} pcs still on PO`" /><em v-if="row.isGroup && row.otherStatuses">+{{ row.otherStatuses }}</em></span>
						</td>
						<template v-if="isUnlinked(row)">
							<td v-for="field in SUMMED_FIELDS" :key="field" class="pd-number" :data-col="field"><template v-if="field === 'ppo_qty' && boxes(row)">{{ formatQuantity(boxes(row)) }}<small class="pd-sub">boxes</small></template><span v-else class="pd-muted">—</span></td>
						</template>
						<template v-else>
							<td v-for="field in SUMMED_FIELDS" :key="field" class="pd-number" :class="{ 'is-negative': field === 'balance' && row.balance < 0 }" :data-col="field">{{ formatQuantity(row[field]) }}<small v-if="field === 'qty' && row.is_set" class="pd-sub" data-set>sets</small><small v-if="field === 'dispatch' && row.to_alternative" class="pd-sub" data-to-alternative>+{{ formatQuantity(row.to_alternative) }} to alternative</small></td>
						</template>
					</tr>
					<tr v-if="shown.hasMore" ref="sentinel" class="pd-more-row"><td :colspan="COLUMNS.length + 1">Loading more {{ unit }}s…</td></tr>
					<tr v-if="!shown.rows.length"><td :colspan="COLUMNS.length + 1" class="pd-empty">No lots match these filters.</td></tr>
				</tbody>
			</table>
		</div>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import { useToast } from "primevue/usetoast"
import { computed, ref } from "vue"

import LotStatusPill from "./LotStatusPill.vue"
import { copyCsv } from "./copyCsv.js"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import { formatQuantity, plural } from "./dashboardFormat.js"
import { LOT_NOT_LINKED, SUMMED_FIELDS, dashboardCsv, groupDashboardRows, rowDrill, sortDashboardRows } from "./dashboardRows.js"
import { useRowWindow } from "./rowWindow.js"

/** Flat lot table (or one row per PPO) with sorting, rows loading as it scrolls, and Copy CSV. */
const props = defineProps({
	rows: { type: Array, required: true },
	ppos: { type: Object, required: true },
	sewingProcesses: { type: Array, default: () => [] },
})
const emit = defineEmits(["drill"])
const toast = useToast()
const COLUMNS = [
	{ key: "ppo", label: "PPO" },
	{ key: "lot", label: "Lot" },
	{ key: "item", label: "Item" },
	{ key: "product_category", label: "Category", title: "Product Category of the lot's item (or its template)" },
	{ key: "status", label: "Status" },
	{ key: "ppo_qty", label: "PPO Qty", isNumber: true, title: "The lot's share of its PPO's pieces, split by the boxes each lot took; set items count sets" },
	{ key: "qty", label: "Lot Qty", isNumber: true, title: "Lot order pieces; a set item counts complete sets" },
	{ key: "cut", label: "Cut Qty", isNumber: true, title: "Pieces received from Cutting Work Orders; a set item counts complete sets (the fewest of its parts per colour and size)" },
	{ key: "stitch", label: "Stitching Qty", isNumber: true, title: "" },
	{ key: "packed", label: "Packed Qty", isNumber: true, title: "Pcs received from the lot's packing Work Orders (Includes Packing); each WO counted once" },
	{ key: "dispatch", label: "Dispatched Qty", isNumber: true, title: "Dispatch pcs (as in PPO Tracking); pieces moved to an alternative lot show below" },
	{ key: "balance", label: "Balance", isNumber: true, title: "PPO Qty − Dispatched − Moved to alternative" },
]
const sort = ref({ key: "ppo", direction: 1 })
const isGrouped = ref(false)

const tableRows = computed(() => (isGrouped.value ? groupDashboardRows(props.rows) : props.rows))
const sorted = computed(() => sortDashboardRows(tableRows.value, sort.value, props.ppos))
const { shown, sentinel } = useRowWindow(sorted)
const unit = computed(() => (isGrouped.value ? "PPO" : "lot"))
const sortLabel = computed(() => COLUMNS.find((column) => column.key === sort.value.key)?.label)
const rangeText = computed(() => (sorted.value.length ? plural(sorted.value.length, unit.value) : `No ${unit.value}s`))

const isUnlinked = (row) => row.status === LOT_NOT_LINKED && !(row.isGroup ? row.lotCount : row.lot)
const rowKey = (row) => (isGrouped.value || !row.lot ? row.ppo : row.lot)
const linkedLots = (row) => row.lots.filter((lot) => lot.lot)
const itemName = (row) => props.ppos[row.ppo]?.item_name
const boxes = (row) => props.ppos[row.ppo]?.boxes

function columnTitle(column) {
	const title = column.key === "stitch"
		? `Pcs received from sewing Work Orders (${props.sewingProcesses.join(", ")}); each WO counted once`
		: column.title
	if (!title) return undefined
	return isGrouped.value && SUMMED_FIELDS.includes(column.key) ? `${title} · summed over the PPO's filtered lots` : title
}

function sortBy(key) {
	sort.value = { key, direction: sort.value.key === key ? -sort.value.direction : 1 }
}

const sortMark = (key) => (sort.value.key === key ? (sort.value.direction > 0 ? "▲" : "▼") : "↕")
const ariaSort = (key) => (sort.value.key === key ? (sort.value.direction > 0 ? "ascending" : "descending") : "none")

function copy() {
	copyCsv(toast, dashboardCsv(sorted.value, isGrouped.value, props.ppos), sorted.value.length, unit.value)
}
</script>
