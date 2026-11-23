import assert from "node:assert/strict"
import test from "node:test"

import { buildFabricPayload, fabricContractLists, hydrateFabricRows } from "../src/departments/fabric-store/fabricCalculate.js"
import {
	getKnittingContractFields, getKnittingContractPayload, isKnittingContract,
} from "../../essdee_yrp/public/js/work_order_knitting_contract.js"

const colours = ["Black", "Navy"]
const dias = ["24 Dia", "26 Dia"]

function knittingRow(overrides = {}) {
	return {
		fabric_row: "FABRIC-1", kind: "knitting", cloth_item: "Cloth", production_detail: "Cloth-1", manual_io: true, reference_routed: true, has_colour: true,
		qty_rows: dias.flatMap((dia) => colours.map((colour) => ({
			key: `${colour}-${dia}`, output_item: "Cloth", output_uom: "Kg", out_attrs: { Dia: dia }, knit_colour: "Greige", label: `${colour} · ${dia}`,
			reference_item_variant: `Cloth-${colour}-${dia}`, prefill: 73, balance: 73, program: 73,
			knitting_inputs: [{ key: "input:0", item: "Yarn", attrs: {}, uom: "Kg", qty_per_output: 1, prefill: 73 }],
		}))),
		...overrides,
	}
}

function floatFields(fields) {
	return fields.filter((field) => field.fieldtype === "Float")
}

test("Desk uses the contract popup only when every fabric row is manual knitting", () => {
	assert.equal(isKnittingContract({ rows: [knittingRow()] }), true)
	assert.equal(isKnittingContract({ rows: [knittingRow(), { kind: "dyeing" }] }), false)
	assert.equal(isKnittingContract({ rows: [] }), false)
})

test("Desk contract fields show one prefilled yarn row and one Greige row per Dia", () => {
	const rows = hydrateFabricRows({ rows: [knittingRow()] })
	const fields = floatFields(getKnittingContractFields(rows))
	assert.deepEqual(fields.map((field) => [field.label, field.default]), [
		["Yarn (Kg)", 146 * 2],
		["Cloth · 24 Dia · Greige (Kg)", 146],
		["Cloth · 26 Dia · Greige (Kg)", 146],
	])
})

test("Desk payload equals the /web payload for the same edited quantities", () => {
	const context = { rows: [knittingRow()] }
	const deskRows = hydrateFabricRows(context)
	const values = Object.fromEntries(floatFields(getKnittingContractFields(deskRows)).map((field) => [field.fieldname, field.default]))
	const [yarnField, firstDiaField] = floatFields(getKnittingContractFields(deskRows))
	values[yarnField.fieldname] = 250
	values[firstDiaField.fieldname] = 100

	const webRows = hydrateFabricRows(context)
	const [deliverables, receivables] = fabricContractLists(webRows[0])
	deliverables.items[0].qty = 250
	receivables.items[0].qty = 100

	const result = getKnittingContractPayload(context, deskRows, values)
	assert.equal(result.error, "")
	assert.deepEqual(result.payload, buildFabricPayload(context, webRows))
	const saved = result.payload.rows[0].entries
	assert.equal(saved.reduce((total, entry) => total + entry.qty, 0), 246)
})

test("Desk payload reports the /web contract error for yarn without fabric", () => {
	const context = { rows: [knittingRow()] }
	const rows = hydrateFabricRows(context)
	const values = Object.fromEntries(floatFields(getKnittingContractFields(rows)).map((field, index) => [field.fieldname, index ? 0 : 50]))
	assert.equal(getKnittingContractPayload(context, rows, values).error, "Enter a fabric receivable quantity before sending Yarn.")
})
