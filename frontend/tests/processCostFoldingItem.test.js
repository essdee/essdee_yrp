import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { processCostLinkFilters, processCostReadOnly } from "../src/departments/merch/process-cost/processCostViews.js"

test("Item is editable on every Lot; only UOM and Supplier Name stay read-only", () => {
	assert.equal(processCostReadOnly("item", {}), false)
	assert.equal(processCostReadOnly("item", { is_folding_lot: false }), false)
	assert.equal(processCostReadOnly("uom", {}), true)
	assert.equal(processCostReadOnly("supplier_name", {}), true)
	assert.equal(processCostReadOnly("supplier", {}), false)
})

test("Item search offers only enabled Items, templates included", () => {
	assert.deepEqual(processCostLinkFilters("item"), { disabled: 0 })
	assert.deepEqual(processCostLinkFilters("tax_slab"), { enabled: 1 })
	assert.deepEqual(processCostLinkFilters("supplier"), {})
})

test("Editor uses the open Item link and keeps the Item when only the Process changes", () => {
	const source = readFileSync(new URL("../src/departments/merch/process-cost/ProcessCostEditor.vue", import.meta.url), "utf8")
	assert.doesNotMatch(source, /item_options|is_cloth_process/)
	assert.match(source, /processCostReadOnly\(key, context\.value\)/)
	assert.match(source, /if \(key === "lot"\) form\.item = null/)
})
