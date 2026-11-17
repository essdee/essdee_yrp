import assert from "node:assert/strict"
import test from "node:test"

const departments = ["accounts", "merch", "merch-pd", "merch-purchase", "planning", "purchase", "quality"]

for (const department of departments) {
	test(`${department} Lot editor edits and saves the Folding Lot flag`, async () => {
		const editor = await import(`../src/departments/${department}/lot/lotEditor.js`)
		const order = editor.LOT_EDIT_GROUPS.find((group) => group.key === "order")
		assert.ok(order.fields.includes("is_folding_lot"))
		const payload = editor.lotSavePayload({ lot_name: "L1", is_folding_lot: 1, lot_fabric_details: [] }, null, [])
		assert.equal(payload.is_folding_lot, 1)
	})
}
