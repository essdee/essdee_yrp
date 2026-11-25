import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"
import { compile } from "@vue/compiler-dom"
import { parse } from "@vue/compiler-sfc"
import { renderToString } from "@vue/server-renderer"
import * as Vue from "vue"

import {
	arrayQuantities, buildFabricMatrices, carryMatrixSelection, fillMatrix, isMatrixAllSelected, isMatrixCellEnabled,
	matrixCellIndex, matrixTotals, moveMatrixFocus, setMatrixAllSelected, setMatrixColumnSelected, setMatrixRowSelected,
} from "../src/departments/fabric-store/fabricMatrix.js"
import { buildFabricPayload, carryFabricMatrixSelection, fabricMatrixQuantities, fabricWarnings, hydrateFabricRows } from "../src/departments/fabric-store/fabricCalculate.js"

const ATTRIBUTES = { colour: "Colour", dia: "Dia" }
const GREIGE = "34's GL Dyed Fabric"

function qtyRow(colour, dia, extra = {}) {
	const planned = extra.planned || dia
	const pool = extra.pool ?? `${GREIGE}-${dia}-Greige`
	return {
		key: `${colour}:${dia}:${planned}`,
		out_attrs: { Colour: colour, Dia: dia },
		target_attrs: { Colour: colour, Dia: planned },
		input_specs: [{ item: extra.input || GREIGE, attrs: { Colour: "Greige", Dia: dia }, qty: 1 }],
		knitting_inputs: [],
		prefill: extra.prefill ?? 0,
		source_available: extra.available ?? null,
		source_pool_key: pool,
		...(extra.source_item_variant ? { matrix_key: `${colour}:${planned}`, source_item_variant: extra.source_item_variant } : {}),
	}
}

/** YRP-WO-2026-00308 shape: 20 Dia planned with a 22 Dia substitute; Maroon has no 16 Dia. */
function dyeingRows() {
	return [
		qtyRow("Black", "20 Dia", { pool: "", available: 0 }),
		qtyRow("Black", "22 Dia", { planned: "20 Dia", available: 414.2, source_item_variant: `${GREIGE}-22 Dia-Greige` }),
		qtyRow("Black", "16 Dia", { available: 284 }),
		qtyRow("Maroon", "20 Dia", { pool: "", available: 0 }),
		qtyRow("Maroon", "22 Dia", { planned: "20 Dia", available: 414.2, source_item_variant: `${GREIGE}-22 Dia-Greige` }),
		qtyRow("Black", "12 Dia", { available: 274 }),
		qtyRow("Maroon", "12 Dia", { available: 274 }),
	]
}

function dyeingContext(rows = dyeingRows()) {
	return { attributes: ATTRIBUTES, rows: [{ fabric_row: "F1", kind: "dyeing", cloth_item: GREIGE, qty_rows: rows }] }
}

test("matrix uses one column per output colour and ascending Dia rows", () => {
	const [matrix] = buildFabricMatrices(dyeingRows(), ATTRIBUTES)
	assert.deepEqual(matrix.columns.map((column) => column.key), ["Black", "Maroon"])
	assert.deepEqual(matrix.rows.map((row) => row.label), ["12 Dia", "16 Dia", "20 Dia", "22 → 20 Dia"])
})

test("actual-Dia substitute rows sit right after their planned Dia", () => {
	const [matrix] = buildFabricMatrices(dyeingRows(), ATTRIBUTES)
	const substitute = matrix.rows[3]
	assert.equal(substitute.substitute, true)
	assert.equal(matrix.rows[2].key, "20 Dia")
	assert.equal(matrixCellIndex(matrix, substitute.key, "Black"), 1)
	assert.equal(matrixCellIndex(matrix, substitute.key, "Maroon"), 4)
})

test("a Dia not made in a colour is not applicable", () => {
	const [matrix] = buildFabricMatrices(dyeingRows(), ATTRIBUTES)
	assert.equal(matrixCellIndex(matrix, "16 Dia", "Maroon"), undefined)
	assert.equal(isMatrixCellEnabled(matrix, "16 Dia", "Maroon"), false)
	assert.equal(isMatrixCellEnabled(matrix, "16 Dia", "Black"), true)
})

test("row availability is the shared greige stock of that Dia", () => {
	const [matrix] = buildFabricMatrices(dyeingRows(), ATTRIBUTES)
	const available = Object.fromEntries(matrix.rows.map((row) => [row.label, row.available]))
	assert.deepEqual(available, { "12 Dia": 274, "16 Dia": 284, "20 Dia": 0, "22 → 20 Dia": 414.2 })
})

test("totals sum rows, columns and grand total without availability flags", () => {
	const [matrix] = buildFabricMatrices(dyeingRows(), ATTRIBUTES)
	const quantities = arrayQuantities([0, 300, 10, 0, 200, 4, 5])
	const totals = matrixTotals(matrix, quantities)
	assert.equal(totals.rows["22 Dia|20 Dia"], 500)
	assert.equal(totals.rows["12 Dia"], 9)
	assert.equal(totals.columns.Black, 314)
	assert.equal(totals.columns.Maroon, 205)
	assert.equal(totals.grand, 519)
	assert.equal(totals.over, undefined)
})

test("unticking a Dia zeroes and disables its cells; reticking keeps them at zero", () => {
	const [matrix] = buildFabricMatrices(dyeingRows(), ATTRIBUTES)
	const values = [0, 300, 10, 0, 200, 4, 5]
	const quantities = arrayQuantities(values)
	setMatrixRowSelected(matrix, "22 Dia|20 Dia", false, quantities)
	assert.deepEqual(values, [0, 0, 10, 0, 0, 4, 5])
	assert.equal(isMatrixCellEnabled(matrix, "22 Dia|20 Dia", "Black"), false)
	setMatrixRowSelected(matrix, "22 Dia|20 Dia", true, quantities)
	assert.equal(isMatrixCellEnabled(matrix, "22 Dia|20 Dia", "Black"), true)
	assert.equal(values[1], 0)
})

test("unticking a colour zeroes and disables every Dia in that colour", () => {
	const [matrix] = buildFabricMatrices(dyeingRows(), ATTRIBUTES)
	const values = [1, 2, 3, 4, 5, 6, 7]
	setMatrixColumnSelected(matrix, "Maroon", false, arrayQuantities(values))
	assert.deepEqual(values, [1, 2, 3, 0, 0, 6, 0])
	assert.equal(isMatrixCellEnabled(matrix, "12 Dia", "Maroon"), false)
	assert.equal(isMatrixAllSelected(matrix), false)
})

test("select all ticks every row and column", () => {
	const [matrix] = buildFabricMatrices(dyeingRows(), ATTRIBUTES)
	const values = [1, 2, 3, 4, 5, 6, 7]
	setMatrixAllSelected(matrix, false, arrayQuantities(values))
	assert.deepEqual(values, [0, 0, 0, 0, 0, 0, 0])
	assert.equal(isMatrixCellEnabled(matrix, "12 Dia", "Black"), false)
	setMatrixAllSelected(matrix, true, arrayQuantities(values))
	assert.equal(isMatrixAllSelected(matrix), true)
})

test("fill writes only cells whose Dia and colour are ticked", () => {
	const [matrix] = buildFabricMatrices(dyeingRows(), ATTRIBUTES)
	const values = [0, 0, 0, 0, 0, 0, 0]
	const quantities = arrayQuantities(values)
	setMatrixColumnSelected(matrix, "Maroon", false, quantities)
	setMatrixRowSelected(matrix, "16 Dia", false, quantities)
	fillMatrix(matrix, quantities, [1, 2, 3, 4, 5, 6, 7])
	assert.deepEqual(values, [1, 2, 0, 0, 0, 6, 0])
})

test("ticks carry to a refilled matrix and its unticked cells stay zero", () => {
	const [previous] = buildFabricMatrices(dyeingRows(), ATTRIBUTES)
	setMatrixColumnSelected(previous, "Maroon", false, arrayQuantities([0, 0, 0, 0, 0, 0, 0]))
	const [next] = buildFabricMatrices(dyeingRows(), ATTRIBUTES)
	const values = [1, 2, 3, 4, 5, 6, 7]
	carryMatrixSelection(next, previous, arrayQuantities(values))
	assert.deepEqual(values, [1, 2, 3, 0, 0, 6, 0])
	assert.equal(isMatrixCellEnabled(next, "20 Dia", "Maroon"), false)
})

test("arrow keys and Enter move to the next enabled cell", () => {
	const [matrix] = buildFabricMatrices(dyeingRows(), ATTRIBUTES)
	assert.deepEqual(moveMatrixFocus(matrix, "12 Dia", "Maroon", "Enter"), { rowKey: "20 Dia", columnKey: "Maroon" })
	assert.deepEqual(moveMatrixFocus(matrix, "20 Dia", "Maroon", "ArrowUp"), { rowKey: "12 Dia", columnKey: "Maroon" })
	assert.deepEqual(moveMatrixFocus(matrix, "16 Dia", "Black", "ArrowRight"), null)
	assert.deepEqual(moveMatrixFocus(matrix, "20 Dia", "Black", "ArrowRight"), { rowKey: "20 Dia", columnKey: "Maroon" })
	assert.deepEqual(moveMatrixFocus(matrix, "20 Dia", "Maroon", "ArrowLeft"), { rowKey: "20 Dia", columnKey: "Black" })
	assert.equal(moveMatrixFocus(matrix, "22 Dia|20 Dia", "Black", "ArrowDown"), null)
})

test("one matrix per input item", () => {
	const rows = [...dyeingRows(), qtyRow("Black", "30 Dia", { input: "Other Greige" })]
	const matrices = buildFabricMatrices(rows, ATTRIBUTES)
	assert.deepEqual(matrices.map((matrix) => matrix.title), [GREIGE, "Other Greige"])
	assert.equal(matrixCellIndex(matrices[1], "30 Dia", "Black"), 7)
})

test("rows that do not fit Dia × Colour keep the old layout", () => {
	assert.equal(buildFabricMatrices([{ ...qtyRow("Black", "20 Dia"), out_attrs: { Colour: "Black" } }], ATTRIBUTES), null)
	assert.equal(buildFabricMatrices([qtyRow("Black", "20 Dia"), qtyRow("Black", "20 Dia")], ATTRIBUTES), null)
	assert.equal(buildFabricMatrices([{ ...qtyRow("Black", "20 Dia"), knitting_inputs: [{ key: "yarn" }] }], ATTRIBUTES), null)
	assert.equal(buildFabricMatrices(dyeingRows(), {}), null)
})

test("hydrated non-knitting rows get matrices; knitting rows do not", () => {
	const [dyeing] = hydrateFabricRows(dyeingContext())
	assert.equal(dyeing.matrices.length, 1)
	const [knitting] = hydrateFabricRows({ attributes: ATTRIBUTES, rows: [{ fabric_row: "K", kind: "knitting", qty_rows: dyeingRows() }] })
	assert.equal(knitting.matrices, null)
})

test("matrix input sends the same Calculate payload as the old per-row inputs", () => {
	const typed = { 1: 300, 2: 10, 4: 200, 6: 5 }
	const [old] = hydrateFabricRows(dyeingContext())
	for (const [index, qty] of Object.entries(typed)) old.entries[index].qty = qty
	const [matrixRow] = hydrateFabricRows(dyeingContext())
	const [matrix] = matrixRow.matrices
	const quantities = fabricMatrixQuantities(matrixRow)
	quantities.set(matrixCellIndex(matrix, "22 Dia|20 Dia", "Black"), 300)
	quantities.set(matrixCellIndex(matrix, "16 Dia", "Black"), 10)
	quantities.set(matrixCellIndex(matrix, "22 Dia|20 Dia", "Maroon"), 200)
	quantities.set(matrixCellIndex(matrix, "12 Dia", "Maroon"), 5)
	const context = dyeingContext()
	assert.deepEqual(buildFabricPayload(context, [matrixRow]), buildFabricPayload(context, [old]))
	const line = buildFabricPayload(context, [matrixRow]).rows[0].entries[0]
	assert.equal(line.matrix_key, "Black:20 Dia")
	assert.equal(line.source_item_variant, `${GREIGE}-22 Dia-Greige`)
})

test("unticked cells are left out of the Calculate payload", () => {
	const [row] = hydrateFabricRows(dyeingContext())
	const [matrix] = row.matrices
	const quantities = fabricMatrixQuantities(row)
	quantities.set(0, 5)
	quantities.set(3, 7)
	setMatrixColumnSelected(matrix, "Maroon", false, quantities)
	const entries = buildFabricPayload(dyeingContext(), [row]).rows[0].entries
	assert.deepEqual(entries.map((entry) => entry.key), [row.entries[0].key])
})

test("refilled /web rows keep previous ticks and zero unticked cells", () => {
	const [previous] = hydrateFabricRows(dyeingContext())
	setMatrixRowSelected(previous.matrices[0], "12 Dia", false, fabricMatrixQuantities(previous))
	const filled = hydrateFabricRows(dyeingContext(dyeingRows().map((row) => ({ ...row, prefill: 9 }))))
	carryFabricMatrixSelection(filled, [previous])
	assert.deepEqual(filled[0].entries.map((entry) => entry.qty), [9, 9, 9, 9, 9, 0, 0])
})

const matrixSource = fs.readFileSync(new URL("../src/departments/fabric-store/FabricDeliverablesMatrix.vue", import.meta.url), "utf8")
const matrixRender = new Function("Vue", compile(parse(matrixSource).descriptor.template.content, { mode: "function" }).code)(Vue)
const panelSource = fs.readFileSync(new URL("../src/departments/fabric-store/WorkOrderActionPanel.vue", import.meta.url), "utf8")
const panelTemplate = parse(panelSource).descriptor.template.content

async function renderMatrix(row) {
	const matrix = row.matrices[0]
	const quantities = fabricMatrixQuantities(row)
	const Root = {
		render: matrixRender,
		data: () => ({ matrix, showTitle: false, drafts: {}, quantities, totals: matrixTotals(matrix, quantities), allSelected: isMatrixAllSelected(matrix) }),
		methods: {
			matrixCellIndex, isMatrixCellEnabled, setMatrixAllSelected, setMatrixColumnSelected, setMatrixRowSelected,
			display: (value) => String(value || 0), cellText: () => "", moveFocus() {}, typeCell() {},
			cellClass: (matrixRow, column) => matrixCellIndex(matrix, matrixRow.key, column.key) === undefined ? "fabric-matrix__cell--na" : isMatrixCellEnabled(matrix, matrixRow.key, column.key) ? "fabric-matrix__cell" : "fabric-matrix__cell--off",
		},
	}
	return renderToString(Vue.createSSRApp(Root))
}

test("matrix renders colour headers, Dia rows, hatched and disabled cells without the old extra text", async () => {
	const [row] = hydrateFabricRows(dyeingContext())
	fabricMatrixQuantities(row).set(1, 500)
	setMatrixRowSelected(row.matrices[0], "16 Dia", false, fabricMatrixQuantities(row))
	const html = await renderMatrix(row)
	assert.match(html, /Use colour Black/)
	assert.match(html, /Use colour Maroon/)
	assert.match(html, /22 → 20 Dia/)
	assert.match(html, /Avail 414.2/)
	assert.doesNotMatch(html, /Avail 0/)
	assert.match(html, /fabric-matrix__cell--na/)
	assert.match(html, /disabled aria-label="Black, 16 Dia, Quantity"/)
	assert.doesNotMatch(html, /fabric-matrix__total--over|More than available/)
	assert.doesNotMatch(html, /Shared|Required|Available output|Stock 1|Quantity to receive/)
})

test("panel shows the matrix instead of per-route cards for matrix rows", () => {
	assert.match(panelTemplate, /<FabricDeliverablesMatrix v-for="\(matrix, index\) in row.matrices"/)
	assert.match(panelTemplate, /v-else-if="row.matrices"/)
})

test("quantities above source GRN availability never warn", () => {
	const [row] = hydrateFabricRows(dyeingContext())
	fabricMatrixQuantities(row).set(1, 500)
	assert.deepEqual(fabricWarnings([row]), [])
	const [old] = hydrateFabricRows({ rows: dyeingContext().rows })
	old.entries[1].qty = 500
	assert.deepEqual(fabricWarnings([old]), [])
})

test("per-colour stock (washing) hides the Dia availability", () => {
	const rows = [
		qtyRow("Maroon", "28 Dia", { pool: "Cloth-28 Dia-Maroon", available: 386.8 }),
		qtyRow("Black", "28 Dia", { pool: "", available: 0 }),
		qtyRow("Maroon", "30 Dia", { pool: "Cloth-30 Dia-Maroon", available: 148.5 }),
	]
	const [matrix] = buildFabricMatrices(rows, ATTRIBUTES)
	assert.equal(matrix.rows[0].available, null)
	assert.equal(matrix.rows[1].available, 148.5)
})
