import assert from "node:assert/strict"
import test from "node:test"
import { correctionItemEditor, hasCorrectionRows } from "../src/departments/fabric-store/workOrderCorrection.js"

test("deliverable editor limits the Item picker to the sanctioned templates", () => {
	assert.deepEqual(correctionItemEditor(["STYLE", "BOX"]).item_filters, { disabled: 0, variant_of: ["is", "not set"], name: ["in", ["STYLE", "BOX"]] })
	assert.deepEqual(correctionItemEditor().item_filters, { disabled: 0, variant_of: ["is", "not set"] })
	assert.deepEqual(correctionItemEditor().dimensions, [])
})

test("only a positive quantity counts as a correction row", () => {
	const groups = (qty) => [{ items: [{ name: "STYLE", values: { S: { qty: 0 }, M: { qty } } }] }]
	assert.equal(hasCorrectionRows(groups(0)), false)
	assert.equal(hasCorrectionRows(groups(4)), true)
	assert.equal(hasCorrectionRows([]), false)
})
