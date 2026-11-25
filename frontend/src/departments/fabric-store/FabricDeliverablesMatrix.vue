<template>
	<section class="fabric-matrix" :aria-label="`Quantity by Dia and Colour${matrix.title ? ` for ${matrix.title}` : ''}`">
		<strong v-if="showTitle" class="fabric-matrix__title">{{ matrix.title }}</strong>
		<div class="fabric-matrix__wrap">
			<table class="fabric-matrix__table">
				<thead>
					<tr>
						<th class="fabric-matrix__dia" scope="col">
							<label class="fabric-matrix__tick"><input type="checkbox" :checked="allSelected" aria-label="Select all Dia and colours" @change="setMatrixAllSelected(matrix, $event.target.checked, quantities)" />Dia</label>
						</th>
						<th v-for="column in matrix.columns" :key="column.key" scope="col" :class="{ 'fabric-matrix__off': !column.selected }">
							<label class="fabric-matrix__tick"><input type="checkbox" :checked="column.selected" :aria-label="`Use colour ${column.label}`" @change="setMatrixColumnSelected(matrix, column.key, $event.target.checked, quantities)" />{{ column.label }}</label>
						</th>
						<th class="fabric-matrix__total" scope="col">Total</th>
					</tr>
				</thead>
				<tbody @keydown="moveFocus">
					<tr v-for="(matrixRow, rowIndex) in matrix.rows" :key="matrixRow.key" :class="{ 'fabric-matrix__off': !matrixRow.selected }">
						<th class="fabric-matrix__dia" scope="row">
							<label class="fabric-matrix__tick"><input type="checkbox" :checked="matrixRow.selected" :aria-label="`Use ${matrixRow.label}`" @change="setMatrixRowSelected(matrix, matrixRow.key, $event.target.checked, quantities)" /><span class="fabric-matrix__dia-name">{{ matrixRow.label }}</span></label>
							<small v-if="matrixRow.available > 0" class="fabric-matrix__avail">Avail {{ display(matrixRow.available) }}</small>
						</th>
						<td v-for="(column, columnIndex) in matrix.columns" :key="column.key" :class="cellClass(matrixRow, column)">
							<input
								v-if="matrixCellIndex(matrix, matrixRow.key, column.key) !== undefined"
								type="text"
								inputmode="decimal"
								placeholder="0"
								:value="cellText(matrixRow, column)"
								:disabled="!isMatrixCellEnabled(matrix, matrixRow.key, column.key)"
								:aria-label="`${column.label}, ${matrixRow.label}, Quantity`"
								:data-row="rowIndex"
								:data-column="columnIndex"
								@focus="$event.target.select()"
								@input="typeCell(matrixRow, column, $event.target.value)"
								@blur="drafts[matrixCellIndex(matrix, matrixRow.key, column.key)] = undefined"
							/>
						</td>
						<td class="fabric-matrix__total">{{ display(totals.rows[matrixRow.key]) }}</td>
					</tr>
				</tbody>
				<tfoot>
					<tr>
						<th class="fabric-matrix__dia" scope="row">Total</th>
						<td v-for="column in matrix.columns" :key="column.key">{{ display(totals.columns[column.key]) }}</td>
						<td class="fabric-matrix__grand">{{ display(totals.grand) }}</td>
					</tr>
				</tfoot>
			</table>
		</div>
	</section>
</template>

<script setup>
import { computed, reactive } from "vue"

import { fabricMatrixQuantities } from "./fabricCalculate.js"
import {
	isMatrixAllSelected, isMatrixCellEnabled, matrixCellIndex, matrixTotals, moveMatrixFocus,
	setMatrixAllSelected, setMatrixColumnSelected, setMatrixRowSelected,
} from "./fabricMatrix.js"

const props = defineProps({
	row: { type: Object, required: true },
	matrix: { type: Object, required: true },
	showTitle: { type: Boolean, default: false },
})
const drafts = reactive({})
const quantities = computed(() => fabricMatrixQuantities(props.row))
const totals = computed(() => matrixTotals(props.matrix, quantities.value))
const allSelected = computed(() => isMatrixAllSelected(props.matrix))

function display(value) {
	return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 })
}

function cellText(matrixRow, column) {
	const index = matrixCellIndex(props.matrix, matrixRow.key, column.key)
	if (drafts[index] !== undefined) return drafts[index]
	const qty = quantities.value.get(index)
	return qty ? String(qty) : ""
}

function cellClass(matrixRow, column) {
	if (matrixCellIndex(props.matrix, matrixRow.key, column.key) === undefined) return "fabric-matrix__cell fabric-matrix__cell--na"
	return isMatrixCellEnabled(props.matrix, matrixRow.key, column.key) ? "fabric-matrix__cell" : "fabric-matrix__cell fabric-matrix__cell--off"
}

function typeCell(matrixRow, column, text) {
	const index = matrixCellIndex(props.matrix, matrixRow.key, column.key)
	drafts[index] = text
	const qty = parseFloat(text)
	quantities.value.set(index, Number.isNaN(qty) || qty < 0 ? 0 : qty)
}

function isCaretAtEdge(input, key) {
	if (key === "ArrowLeft") return input.selectionStart === 0
	if (key === "ArrowRight") return input.selectionEnd === input.value.length
	return true
}

function moveFocus(event) {
	const input = event.target
	if (input.tagName !== "INPUT" || input.type !== "text" || !isCaretAtEdge(input, event.key)) return
	const matrixRow = props.matrix.rows[Number(input.dataset.row)]
	const column = props.matrix.columns[Number(input.dataset.column)]
	const next = moveMatrixFocus(props.matrix, matrixRow.key, column.key, event.key)
	if (event.key === "Enter") event.preventDefault()
	if (!next) return
	event.preventDefault()
	const rowIndex = props.matrix.rows.findIndex((row) => row.key === next.rowKey)
	const columnIndex = props.matrix.columns.findIndex((candidate) => candidate.key === next.columnKey)
	input.closest("tbody").querySelector(`input[data-row="${rowIndex}"][data-column="${columnIndex}"]`)?.focus()
}
</script>

<style scoped>
.fabric-matrix { display: grid; gap: var(--erp-space-2); min-width: 0; }
.fabric-matrix__title { font-size: var(--erp-font-size-caption); color: var(--erp-text-secondary); }
.fabric-matrix__wrap { overflow: auto; max-height: min(60vh, 560px); border: 1px solid var(--erp-border-strong); border-radius: var(--erp-control-radius); overscroll-behavior: contain; background: var(--erp-surface); }
.fabric-matrix__table { width: 100%; border-collapse: separate; border-spacing: 0; font-variant-numeric: tabular-nums; font-size: var(--erp-font-size-table); }
.fabric-matrix__table th, .fabric-matrix__table td { padding: 0; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); background: var(--erp-surface); }
.fabric-matrix__table tr > :last-child { border-right: 0; }
.fabric-matrix__table thead th { position: sticky; top: 0; z-index: 2; padding: 8px 10px; background: var(--erp-surface-muted); color: var(--erp-text-secondary); font-weight: 600; text-align: right; white-space: nowrap; border-bottom-color: var(--erp-border-strong); }
.fabric-matrix__table .fabric-matrix__dia { position: sticky; left: 0; z-index: 1; min-width: 104px; padding: 6px 10px; background: var(--erp-surface-muted); text-align: left; border-right-color: var(--erp-border-strong); }
.fabric-matrix__table thead .fabric-matrix__dia, .fabric-matrix__table tfoot .fabric-matrix__dia { z-index: 3; }
.fabric-matrix__tick { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
.fabric-matrix__tick input { margin: 0; accent-color: var(--erp-accent); }
.fabric-matrix__dia-name { font-weight: 600; color: var(--erp-text); white-space: nowrap; }
.fabric-matrix__avail { display: block; margin: 1px 0 0 19px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); white-space: nowrap; }
.fabric-matrix__cell { min-width: 92px; }
.fabric-matrix__cell input { width: 100%; padding: 9px 10px; border: 0; outline: 0; background: transparent; color: var(--erp-text); font: inherit; text-align: right; }
.fabric-matrix__cell input::placeholder { color: var(--erp-text-muted); opacity: 0.6; }
.fabric-matrix__cell:hover { background: var(--erp-surface-hover); }
.fabric-matrix__cell:focus-within { box-shadow: inset 0 0 0 2px var(--erp-accent); }
.fabric-matrix__table .fabric-matrix__cell--na { background: repeating-linear-gradient(135deg, var(--erp-surface-muted) 0 6px, var(--erp-surface) 6px 12px); }
.fabric-matrix__table .fabric-matrix__cell--off { background: var(--erp-surface-muted); }
.fabric-matrix__cell--off input { color: var(--erp-text-muted); cursor: not-allowed; }
.fabric-matrix__off .fabric-matrix__dia-name, thead .fabric-matrix__off { color: var(--erp-text-muted); }
.fabric-matrix__total, .fabric-matrix__table tfoot td { min-width: 80px; padding: 8px 10px !important; text-align: right; color: var(--erp-text-secondary); font-weight: 500; white-space: nowrap; }
.fabric-matrix__table tfoot th, .fabric-matrix__table tfoot td { position: sticky; bottom: 0; z-index: 2; background: var(--erp-surface-muted); border-top: 1px solid var(--erp-border-strong); border-bottom: 0; }
.fabric-matrix__grand { color: var(--erp-text) !important; font-weight: 650 !important; }
@media (max-width: 640px) { .fabric-matrix__table .fabric-matrix__dia { min-width: 84px; } .fabric-matrix__cell { min-width: 80px; } }
</style>
