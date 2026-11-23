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
	assert.deepEqual(processCostLinkFilters("item", { item_options: null, is_folding_lot: true }), { disabled: 0 })
	assert.deepEqual(processCostLinkFilters("tax_slab"), { enabled: 1 })
	assert.deepEqual(processCostLinkFilters("supplier"), {})
})

test("Editor keeps the chosen Item and prefills it from the Lot only when a Lot is picked with no Item", () => {
	const source = readFileSync(new URL("../src/departments/merch/process-cost/ProcessCostEditor.vue", import.meta.url), "utf8")
	assert.doesNotMatch(source, /item_options|is_cloth_process/)
	assert.match(source, /processCostReadOnly\(key, context\.value\)/)
	assert.doesNotMatch(source, /form\.item = null/)
	assert.match(source, /refreshContext\(true, key === "lot" && !form\.item\)/)
	assert.match(source, /getProcessCostGrid\(form, prefillItem\)/)
	assert.match(source, /if \(saving\.value \|\| field\.read_only\) return true/)
})

test("With a Lot, Item search offers only the Lot Item and its fabric Items", () => {
	assert.deepEqual(processCostLinkFilters("item", { item_options: ["Garment", "25's OE Cloth"] }), { disabled: 0, name: ["in", ["Garment", "25's OE Cloth"]] })
	assert.deepEqual(processCostLinkFilters("item", { item_options: [] }), { disabled: 0, name: ["in", [""]] })
	const source = readFileSync(new URL("../src/departments/merch/process-cost/ProcessCostEditor.vue", import.meta.url), "utf8")
	assert.match(source, /link_filters: processCostLinkFilters\(key, context\.value\)/)
})
