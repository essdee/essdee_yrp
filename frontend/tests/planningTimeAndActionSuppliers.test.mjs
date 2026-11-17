import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import {
	plannedSupplierValues, supplierChipTitle, supplierChipTone, withoutEmptySuppliers,
} from "../src/departments/planning/time-and-action/supplierChips.js"

const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

const workOrder = { doctype: "YRP Work Order", supplier: "SUP-1", documents: ["WO-1", "WO-2"], delivered: 1500, received: 900 }
const purchaseOrder = { doctype: "Purchase Order", supplier: "SUP-1", documents: ["PO-7"], ordered: 250.5, received: 0 }

test("planned suppliers without actual work are hollow; unplanned actual suppliers stand apart", () => {
	assert.equal(supplierChipTone({ is_planned: 1, actuals: [] }), "hollow")
	assert.equal(supplierChipTone({ is_planned: 1, actuals: [workOrder] }), "planned")
	assert.equal(supplierChipTone({ is_planned: 0, actuals: [workOrder] }), "unplanned")
})

test("chip tooltip shows Work Order delivered/received and PO ordered/received", () => {
	const chip = { supplier: "SUP-1", supplier_name: "Sri Knits", is_planned: 1, actuals: [workOrder, purchaseOrder] }
	assert.equal(
		supplierChipTitle(chip),
		"Sri Knits (SUP-1) · Planned\nWork Orders WO-1, WO-2: delivered 1,500, received 900\nPurchase Order PO-7: ordered 250.5, received 0",
	)
})

test("chip tooltip says when a planned supplier has no work yet, or a supplier was not planned", () => {
	assert.equal(
		supplierChipTitle({ supplier: "SUP-2", supplier_name: "SUP-2", is_planned: 1, actuals: [] }),
		"SUP-2 · Planned\nNo Work Order or Purchase Order yet",
	)
	assert.match(supplierChipTitle({ supplier: "SUP-3", supplier_name: "Dye House", is_planned: 0, actuals: [workOrder] }), /^Dye House \(SUP-3\) · Not planned\n/)
})

test("planned supplier values come from the planned chips only", () => {
	const chips = [{ supplier: "SUP-1", is_planned: 1 }, { supplier: "SUP-9", is_planned: 0 }, { supplier: "SUP-2", is_planned: 1 }]
	assert.deepEqual(plannedSupplierValues(chips), ["SUP-1", "SUP-2"])
	assert.deepEqual(plannedSupplierValues(undefined), [])
})

test("create sends only actions of the previewed master that have planned suppliers", () => {
	const planned = { Knitting: ["SUP-1"], Dyeing: [], Cutting: null, Printing: ["SUP-2"] }
	assert.deepEqual(withoutEmptySuppliers(planned, ["Knitting", "Dyeing", "Cutting"]), { Knitting: ["SUP-1"] })
})

test("supplier API sends string args and create sends planned suppliers as JSON", () => {
	const api = source("api/timeAndAction.js")
	assert.match(api, /const SUPPLIERS = "essdee_yrp.time_and_action.suppliers"/)
	assert.match(api, /\$\{SUPPLIERS\}\.get_supplier_chips`, \{ time_and_action: timeAndAction \}/)
	assert.match(api, /\$\{SUPPLIERS\}\.set_planned_suppliers`, \{ time_and_action: timeAndAction, action, suppliers: JSON.stringify\(suppliers\) \}/)
	assert.match(api, /planned_suppliers: JSON.stringify\(plannedSuppliers \|\| \{\}\)/)
})

test("editor shows supplier chips per action and edits planned suppliers while allowed", () => {
	const editor = source("departments/planning/time-and-action/TimeAndActionEditor.vue")
	const table = source("departments/planning/time-and-action/TimeAndActionTable.vue")
	assert.match(table, /<SupplierChips v-if="chips\[row.action\]\?.length \|\| canEditSuppliers" :chips="chips\[row.action\]"/)
	assert.match(editor, /:can-edit-suppliers="Boolean\(data.can_edit_suppliers\)"/)
	assert.match(editor, /<PlannedSuppliersDialog/)
	const chips = source("departments/planning/time-and-action/SupplierChips.vue")
	assert.match(chips, /supplierChipTitle\(chip\)/)
	assert.match(chips, /`ta-supplier--\$\{supplierChipTone\(chip\)\}`/)
})

test("create preview offers Planned Suppliers next to Work Station", () => {
	const dialog = source("departments/planning/time-and-action/CreateTimeAndActionDialog.vue")
	assert.match(dialog, /<th class="ta-create__station">Work Station<\/th><th class="ta-create__suppliers">Planned Suppliers<\/th>/)
	assert.match(dialog, /<LinkMultiSelectField v-model="plannedSuppliers\[row.action\]" doctype="Supplier"/)
	assert.match(dialog, /withoutEmptySuppliers\(plannedSuppliers.value, preview.value.rows.map\(\(row\) => row.action\)\)/)
})
