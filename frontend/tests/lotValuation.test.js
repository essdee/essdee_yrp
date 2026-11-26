import assert from "node:assert/strict"
import test from "node:test"

import {
	VALUATION_TAB,
	addColumns,
	formatAdd,
	hasRateSections,
	howToRead,
	itemTags,
	packedBoxes,
	rateReconciliation,
	shortDoc,
	valuationTabs,
	waterfallRows,
} from "../src/departments/merch/lot/valuation/lotValuation.js"
import { rateOutHover } from "../src/departments/merch/lot/valuation/valuationHoverContent.js"

const boxRow = (item, qty, total) => ({ item, qty, total, rate_out: total / qty, pieces_per_box: 5, rate_out_piece: total / qty / 5 })
const result = {
	root_stage: "Ironing and Packing",
	summary: { qty: 55, uom: "Pieces", ledger_value: 5535.33893, categories: { unattributed: 0 }, checks: { unexplained_value: 0 } },
	rate_sections: {
		pieces_per_box: 5,
		has_unattributed: false,
		root_total: 5535.338927,
		sections: [{ id: "Yarn purchase", rows: [] }, { id: "Ironing and Packing", rows: [boxRow("L", 6, 2980.19), boxRow("M", 5, 2555.148927)] }],
	},
}

test("Valuation tab is added only for System Managers", () => {
	const tabs = [{ key: "lot", label: "Summary" }]
	assert.deepEqual(valuationTabs(tabs, false), tabs)
	assert.deepEqual(valuationTabs(tabs, true).at(-1), VALUATION_TAB)
})

test("every section shares the same addition columns; unattributed only when the lot has any", () => {
	assert.deepEqual(addColumns(result.rate_sections).map((column) => column.label), ["+ Process cost", "+ Accessories", "+ PI adjustment", "+ WO close"])
	assert.equal(addColumns({ has_unattributed: true }).at(-1).key, "unattributed")
})

test("additions show a dash for zero and a sign otherwise", () => {
	assert.equal(formatAdd(0.001), "—")
	assert.equal(formatAdd(20), "+₹20.00")
	assert.equal(formatAdd(-1.5), "−₹1.50")
})

test("packed root leads with boxes and a per-box rate per size", () => {
	const boxes = packedBoxes(result.rate_sections)
	assert.equal(boxes.boxes, 11)
	assert.deepEqual(boxes.sizes.map((size) => [size.item, size.boxes, size.rate.toFixed(2)]), [["L", 6, "496.70"], ["M", 5, "511.03"]])
	assert.equal(packedBoxes({ ...result.rate_sections, pieces_per_box: 0 }), null)
	assert.match(howToRead(result), /11 boxes \(55 pieces\).*per box of 5 pieces/)
})

test("reconciliation compares the root total with the ledger to the paisa", () => {
	const check = rateReconciliation(result)
	assert.equal(check.ok, true)
	assert.equal(check.difference, 0)
	assert.equal(rateReconciliation({ ...result, summary: { ...result.summary, ledger_value: 5536 } }).ok, false)
})

test("old cached results without the rate build-up ask for a recalculation", () => {
	assert.equal(hasRateSections(result), true)
	assert.equal(hasRateSections({ summary: {}, nodes: {} }), false)
})

test("rows going on only at work order close are tagged with their destination", () => {
	assert.deepEqual(itemTags({ to: [{ stage: "Stitching", wo_close: true }] }).map((tag) => tag.label), ["→ Stitching (WO close)"])
	assert.deepEqual(itemTags({ residual: "Lineage missing", to: [] }).map((tag) => tag.label), ["Lineage missing"])
})

test("rate out hover adds the fixed columns up to the rate out", () => {
	const row = { rate_in: 300, process: 0, accessories: 0, pi: 20, wo_close: 0, rate_out: 320, to: [{ stage: "Knitting", wo_close: false }] }
	const hover = rateOutHover(row, addColumns(result.rate_sections))
	assert.deepEqual(hover.rows.map((line) => line.value), ["₹300.00", "—", "—", "+₹20.00", "—", "₹320.00"])
	assert.equal(shortDoc("YRP-GRN-2026-00774"), "GRN-00774")
})

test("waterfall bars start where the previous stage ended", () => {
	const { rows, total } = waterfallRows({ waterfall: [{ stage: "Yarn", value: 60 }, { stage: "Knitting cost", value: 40 }] })
	assert.equal(total, 100)
	assert.deepEqual(rows.map((row) => [row.category, row.left, row.width]), [["material", 0, 60], ["process", 60, 40]])
})
