import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"

import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as workOrderTotals from "../src/departments/fabric-store/workOrderTotals.js"

const read = (path) => fs.readFileSync(new URL(`../src/departments/${path}`, import.meta.url), "utf8")
const Link = { props: ["name"], setup: (props) => () => Vue.h("span", props.name) }
const textOf = (node) => findNodes(node, () => true).map((child) => child.text).join("").trim()

function mountMatrix(secondaryQty) {
	const Matrix = loadComponent("frontend/src/departments/fabric-store/WorkOrderItemMatrix.vue", { "../../components/common/DocumentLink.vue": Link, "./workOrderTotals.js": workOrderTotals })
	const item = (dia, qty, secondary) => ({ name: "Cloth", attributes: { Dia: dia, Colour: "Black" }, secondary_uom: "Roll", values: { default: { qty, pending_quantity: qty, secondary_qty: secondary, secondary_uom: "Roll" } } })
	return mountComponent(Matrix, { groups: [{ attributes: ["Dia", "Colour"], primary_attribute_values: [], items: [item("22 Dia", 100, secondaryQty), item("16 Dia", 50, 0)] }] })
}

test("Work Order matrix shows the secondary quantity with its UOM", () => {
	const root = mountMatrix(12)
	const headings = findNodes(root, (node) => node.type === "th").map(textOf)
	assert.ok(headings.includes("Secondary Qty"))
	const cells = findNodes(root, (node) => node.type === "td").map(textOf)
	assert.ok(cells.includes("12 Roll"))
	assert.ok(cells.includes("—"))
})

test("Work Order matrix hides the secondary column when none is entered", () => {
	const root = mountMatrix(0)
	assert.ok(!findNodes(root, (node) => node.type === "th").map(textOf).includes("Secondary Qty"))
})

test("Secondary Qty dialog loads and saves through the Work Order commands, also after submit", () => {
	const dialog = read("fabric-store/WorkOrderSecondaryQtyDialog.vue")
	assert.match(dialog, /executeWorkOrderCommand\(props\.workOrder\.name, "get_secondary_quantities"\)/)
	assert.match(dialog, /"update_secondary_quantities", \{ quantities \}/)
	const page = read("FabricWorkOrder.vue")
	assert.match(page, /add\("edit_secondary_qty", "Secondary Qty"/)
	assert.match(page, /<WorkOrderSecondaryQtyDialog v-model:visible="secondaryQtyVisible"/)
})
