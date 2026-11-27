import assert from "node:assert/strict"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent, typeInto } from "../../scripts/helpers/vue_renderer.mjs"
import * as stockItemComposer from "../src/utils/stockItemComposer.js"
import * as stockItemTotals from "../src/engine/stock/stockItemTotals.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const rootPath = fileURLToPath(new URL("../../", import.meta.url))
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const Button = (props) => Vue.h("button", props, props.label)
const schema = { item: "Shirt", primary_attribute: "Size", primary_attribute_values: ["S", "M"], attributes: [], default_uom: "Nos" }
const Composer = loadComponent(resolve(rootPath, "frontend/src/components/stock/StockItemComposer.vue"), {
	"primevue/button": Button, "primevue/message": (props) => Vue.h("control", props), "../../components/common/LinkField.vue": (props) => Vue.h("link-field", props),
	"../../utils/stockItemComposer.js": stockItemComposer, "../../engine/stock/stockItemTotals.js": stockItemTotals,
	"../../utils/dateFormat.js": { formatDisplayDate: (value) => value || "—" }, "../../api/frappe.js": { callMethod: async () => [] },
})

test("editing a saved count keeps uncounted and cleared sizes blank", async () => {
	const savedRow = { name: "Shirt", dimensions: {}, attributes: {}, primary_attribute: "Size", default_uom: "Nos", values: { S: { qty: 5, rate: 12 }, M: { qty: null, rate: 0 } } }
	const modelValue = [{ attributes: [], primary_attribute: "Size", primary_attribute_values: ["S", "M"], items: [savedRow] }]
	const props = Vue.reactive({ operation: "stock_reconciliation", editor: { dimensions: [] }, modelValue, schemaLoader: async () => structuredClone(schema), "onUpdate:modelValue": (value) => { props.modelValue = value } })
	const root = mountComponent(Composer, props)
	await tick()
	findNodes(root, node => node.type === "button" && node.props["aria-label"] === "Edit Shirt")[0].props.onClick()
	await tick()
	const sizeM = findNodes(root, node => node.type === "input" && node.props["aria-label"] === "Counted Qty M")[0]
	typeInto(sizeM, 3)
	typeInto(sizeM, "")
	await tick()
	findNodes(root, node => node.type === "button" && node.props.label === "Update Item")[0].props.onClick()
	await tick()

	const values = props.modelValue[0].items[0].values
	assert.equal(values.S.qty, 5)
	assert.equal(values.M.qty, null)
})
