import assert from "node:assert/strict"
import test from "node:test"
import fs from "node:fs"

import { FOLDING_ROW_EDITOR, isFoldingContext, workOrderRequiredFields } from "../src/departments/fabric-store/workOrderFolding.js"

const read = (path) => fs.readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

test("folding Work Orders do not require an Item or Production Detail", () => {
	const fields = ["naming_series", "supplier", "lot", "item", "production_detail"]
	assert.deepEqual(workOrderRequiredFields(fields, true), ["naming_series", "supplier", "lot"])
	assert.deepEqual(workOrderRequiredFields(fields, false), fields)
})

test("folding context comes from the selection context or the Lot", () => {
	assert.equal(isFoldingContext({ is_folding_lot: true }), true)
	assert.equal(isFoldingContext({ is_folding_lot: 1 }), true)
	assert.equal(isFoldingContext({}), false)
	assert.equal(isFoldingContext(null), false)
})

test("folding rows pick any non-variant Item without stock dimensions", () => {
	assert.deepEqual(FOLDING_ROW_EDITOR.dimensions, [])
	assert.deepEqual(FOLDING_ROW_EDITOR.item_filters, { disabled: 0, variant_of: ["is", "not set"] })
})

test("Work Order editor lets folding users enter deliverables and receivables manually", () => {
	const editor = read("departments/fabric-store/WorkOrderEditor.vue")
	assert.match(editor, /<StockItemComposer v-model="deliverableDetails" operation="work_order"/)
	assert.match(editor, /<StockItemComposer v-model="receivableDetails" operation="work_order"/)
	assert.match(editor, /:schema-loader="loadFoldingItemSchema"/)
	assert.match(editor, /v-if="foldingLot"/)
	assert.match(read("api/fabricStore.js"), /get_work_order_item_schema/)
})

test("folding row tables stay editable so selected rows can be deleted", () => {
	const editor = read("departments/fabric-store/WorkOrderEditor.vue")
	const composers = editor.match(/<StockItemComposer [^>]*operation="work_order"[^>]*>/g)
	assert.equal(composers.length, 2)
	for (const composer of composers) assert.doesNotMatch(composer, /read-only/)
	const composer = read("components/stock/StockItemComposer.vue")
	assert.match(composer, /<footer v-if="rowSelection.selected.value.length" class="stock-composer__selection-footer">/)
	assert.match(composer, /<Button label="Delete" icon="pi pi-trash"[^>]*@click="deleteSelected" \/>/)
})
