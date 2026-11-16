import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const source = readFileSync(new URL("../src/departments/fabric-store/DeliveryChallanWorkspace.vue", import.meta.url), "utf8")

function editGates({ specialSource, canEditDraft = true, editingSubmitted = false, allowOnSubmit = [] }) {
	const functions = source.match(/function canEditMatrixBlock\(kind\) \{[\s\S]*?\n\}\nfunction canEditSecondaryQuantity\(kind\) \{[\s\S]*?\n\}/)[0]
	const state = {
		workspace: { value: { special_source: specialSource } },
		canEdit: { value: canEditDraft || editingSubmitted },
		canEditDraft: { value: canEditDraft },
		editingSubmitted: { value: editingSubmitted },
		allowOnSubmitFields: { value: new Set(allowOnSubmit) },
	}
	return new Function(...Object.keys(state), `${functions}\nreturn { canEditMatrixBlock, canEditSecondaryQuantity }`)(...Object.values(state))
}

test("CPM draft keeps primary quantity locked but allows secondary quantity", () => {
	const gates = editGates({ specialSource: { active: true, read_only: true, secondary_qty_editable: true } })
	assert.equal(gates.canEditMatrixBlock("items"), false)
	assert.equal(gates.canEditSecondaryQuantity("items"), true)
	assert.equal(gates.canEditSecondaryQuantity("corrections"), false)
})

test("other source-managed DCs and submitted CPM DCs keep secondary quantity locked", () => {
	assert.equal(editGates({ specialSource: { active: true, read_only: true, secondary_qty_editable: false } }).canEditSecondaryQuantity("items"), false)
	assert.equal(editGates({ specialSource: { active: true, read_only: true, secondary_qty_editable: true }, canEditDraft: false }).canEditSecondaryQuantity("items"), false)
})

test("ordinary DCs keep the shared matrix gate for secondary quantity", () => {
	assert.equal(editGates({ specialSource: { active: false, read_only: false } }).canEditSecondaryQuantity("items"), true)
	assert.equal(editGates({ specialSource: { active: false, read_only: false }, canEditDraft: false }).canEditSecondaryQuantity("items"), false)
	assert.equal(editGates({ specialSource: { active: false }, canEditDraft: false, editingSubmitted: true, allowOnSubmit: ["items"] }).canEditSecondaryQuantity("items"), true)
	assert.equal((source.match(/:disabled="!canEditSecondaryQuantity\(block\.kind\)"/g) || []).length, 2)
})
