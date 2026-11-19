import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { processCostLinkFilters, processCostReadOnly } from "../src/departments/merch/process-cost/processCostViews.js"

test("Item is read-only from the Lot unless the Lot is a Folding Lot", () => {
	assert.equal(processCostReadOnly("item", {}), true)
	assert.equal(processCostReadOnly("item", { is_folding_lot: false }), true)
	assert.equal(processCostReadOnly("item", { is_folding_lot: true }), false)
	assert.equal(processCostReadOnly("uom", { is_folding_lot: true }), true)
	assert.equal(processCostReadOnly("supplier", {}), false)
})

test("Item search offers only enabled Items, templates included", () => {
	assert.deepEqual(processCostLinkFilters("item"), { disabled: 0 })
	assert.deepEqual(processCostLinkFilters("tax_slab"), { enabled: 1 })
	assert.deepEqual(processCostLinkFilters("supplier"), {})
})

test("Folding Lot editor uses the open Item link instead of the cloth Item select", () => {
	const source = readFileSync(new URL("../src/departments/merch/process-cost/ProcessCostEditor.vue", import.meta.url), "utf8")
	assert.match(source, /context\.is_cloth_process && !context\.is_folding_lot/)
	assert.match(source, /processCostReadOnly\(key, context\.value\)/)
})
