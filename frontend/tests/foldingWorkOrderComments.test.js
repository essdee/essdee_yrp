import assert from "node:assert/strict"
import test from "node:test"
import fs from "node:fs"
import { fileURLToPath } from "node:url"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent, typeInto } from "../../scripts/helpers/vue_renderer.mjs"
import * as stockItemComposer from "../src/utils/stockItemComposer.js"
import * as stockItemTotals from "../src/engine/stock/stockItemTotals.js"
import * as workOrderTotals from "../src/departments/fabric-store/workOrderTotals.js"
import { FOLDING_ROW_EDITOR } from "../src/departments/fabric-store/workOrderFolding.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const rootPath = fileURLToPath(new URL("../../", import.meta.url))
const read = (path) => fs.readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const text = (root) => findNodes(root, () => true).map((node) => node.text).join(" ")
const Button = (props) => Vue.h("button", props, props.label)
const LinkField = (props) => Vue.h("link-field", props)
const Message = (props, { slots }) => Vue.h("message", props, slots.default?.())
const Link = { props: ["name", "label"], setup: (props) => () => Vue.h("span", props.label || props.name) }
const schema = { item: "Towel", attributes: ["Colour"], attribute_values: { Colour: ["Red"] }, default_uom: "Nos" }

function mountComposer(extraProps = {}) {
	const component = loadComponent(resolve(rootPath, "frontend/src/components/stock/StockItemComposer.vue"), {
		"primevue/button": Button, "primevue/message": Message, "../../components/common/LinkField.vue": LinkField,
		"../../utils/stockItemComposer.js": stockItemComposer, "../../engine/stock/stockItemTotals.js": stockItemTotals,
		"../../api/frappe.js": { callMethod: async () => [] },
	})
	const props = Vue.reactive({ operation: "work_order", editor: FOLDING_ROW_EDITOR, modelValue: [], schemaLoader: async () => structuredClone(schema), ...extraProps, "onUpdate:modelValue": (value) => { props.modelValue = value } })
	return { root: mountComponent(component, props), props }
}
const button = (root, label) => findNodes(root, (node) => node.type === "button" && node.props.label === label)[0]
const link = (root, label) => findNodes(root, (node) => node.type === "link-field" && node.props.label === label)[0]
const textarea = (root) => findNodes(root, (node) => node.type === "textarea")[0]
const headers = (root) => findNodes(root, (node) => node.type === "th").map((node) => text(node).trim())

async function addRow(root, comment) {
	link(root, "Item *").props["onUpdate:modelValue"]("Towel")
	await tick()
	button(root, "Get Item").props.onClick()
	await tick()
	link(root, "Colour *").props["onUpdate:modelValue"]("Red")
	typeInto(findNodes(root, (node) => node.type === "input" && node.props.type === "number")[0], 4)
	typeInto(textarea(root), comment)
	await tick()
	await button(root, "OK · Add Item").props.onClick()
	await tick()
}

test("folding row composer saves an optional comment per row and shows it as a column", async () => {
	const { root, props } = mountComposer({ rowComments: true })
	await addRow(root, "  Fold in half  ")
	await addRow(root, "")
	const rows = props.modelValue.flatMap((group) => group.items)
	assert.deepEqual(rows.map((row) => row.comments), ["Fold in half", ""])
	assert.ok(headers(root).includes("Comments"))
	assert.ok(text(root).includes("Fold in half"))
	assert.equal(textarea(root).value, "", "comment resets after Add")

	findNodes(root, (node) => node.type === "button" && node.props.title === "Edit item")[0].props.onClick()
	await tick()
	await tick()
	assert.equal(textarea(root).value, "Fold in half", "editing a row loads its comment")
})

test("composers without row comments keep their existing layout", async () => {
	const { root, props } = mountComposer()
	assert.equal(textarea(root), undefined)
	await addRow(root, "").catch(() => {})
	assert.ok(!headers(root).includes("Comments"))
	assert.equal(props.modelValue.flatMap((group) => group.items)[0]?.comments, undefined)
})

test("folding Work Order editor turns on row comments for deliverables and receivables", () => {
	const composers = read("departments/fabric-store/WorkOrderEditor.vue").match(/<StockItemComposer [^>]*operation="work_order"[^>]*>/g)
	assert.equal(composers.length, 2)
	for (const composer of composers) assert.match(composer, / row-comments /)
})

test("Work Order matrix shows a Comments column only when a row has a comment", () => {
	const Matrix = loadComponent(resolve(rootPath, "frontend/src/departments/fabric-store/WorkOrderItemMatrix.vue"), { "../../components/common/DocumentLink.vue": Link, "./workOrderTotals.js": workOrderTotals })
	const plain = { attributes: ["Colour"], items: [{ name: "Towel", attributes: { Colour: "Red" }, values: { default: { qty: 4 } } }] }
	assert.ok(!headers(mountComponent(Matrix, { groups: [plain] })).includes("Comments"))

	const commented = structuredClone(plain)
	commented.items[0].comments = "Fold in half"
	const root = mountComponent(Matrix, { groups: [commented] })
	assert.ok(headers(root).includes("Comments"))
	assert.ok(text(root).includes("Fold in half"))

	const sized = { attributes: ["Colour", "Size"], primary_attribute: "Size", primary_attribute_values: ["S", "M"], items: [{ name: "Towel", attributes: { Colour: "Red" }, comments: "Pack flat", values: { S: { qty: 1 }, M: { qty: 2 } } }] }
	const sizedRoot = mountComponent(Matrix, { groups: [sized] })
	assert.ok(headers(sizedRoot).includes("Comments"))
	assert.ok(text(sizedRoot).includes("Pack flat"))
	assert.ok(!headers(mountComponent(Matrix, { groups: [sized], mode: "summary" })).includes("Comments"))
})
