import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"
import { syncItemProductionOrderRows } from "../src/departments/fabric-store/purchaseOrderProductionOrders.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const names = (rows) => rows.map((row) => row.production_order)

test("row PPOs append once in pick order and never remove loaded table rows", () => {
	const loaded = [{ production_order: "PPO-4", item_name: "SET" }]
	const rows = syncItemProductionOrderRows(loaded, ["PPO-4"], ["PPO-1", "PPO-2", "PPO-1", "", "PPO-3"], new Map([["PPO-2", "VEST"]]))
	assert.deepEqual(rows, [
		{ production_order: "PPO-4", item_name: "SET" },
		{ production_order: "PPO-1", item_name: "" },
		{ production_order: "PPO-2", item_name: "VEST" },
		{ production_order: "PPO-3", item_name: "" },
	])
	assert.deepEqual(names(syncItemProductionOrderRows(rows, ["PPO-4"], ["PPO-1", "PPO-2", "PPO-3"])), ["PPO-4", "PPO-1", "PPO-2", "PPO-3"])
	assert.deepEqual(names(syncItemProductionOrderRows(loaded, ["PPO-4"], [])), ["PPO-4"])
})

test("a re-picked PPO replaces only the unsaved one it was added for and fills its item later", () => {
	const picked = syncItemProductionOrderRows([{ production_order: "PPO-4", item_name: "SET" }], ["PPO-4"], ["PPO-1"])
	const repicked = syncItemProductionOrderRows(picked, ["PPO-4"], ["PPO-2"])
	assert.deepEqual(names(repicked), ["PPO-4", "PPO-2"])
	const named = syncItemProductionOrderRows(repicked, ["PPO-4"], ["PPO-2"], new Map([["PPO-2", "VEST"]]))
	assert.equal(named[1].item_name, "VEST")
	assert.deepEqual(names(syncItemProductionOrderRows([{ production_order: "PPO-4" }], ["PPO-4"], ["PPO-4"])), ["PPO-4"])
})

test("/web item entry shows Production Order only for approval items and syncs the PPO table live", () => {
	const editor = source("../src/departments/fabric-store/PurchaseOrderEditor.vue")
	const field = editor.match(/<LinkField\s+v-if="schema\?\.is_production_order_item"[\s\S]*?\/>/)?.[0]
	assert.ok(field, "Production Order entry field")
	assert.match(field, /doctype="YRP Production Order"/)
	assert.match(field, /label="Production Order"/)
	assert.doesNotMatch(field, /\brequired\b/)
	assert.match(field, /@update:model-value="setItemProductionOrder\(values, \$event\)"/)
	assert.match(field, /@select="rememberProductionOrderItem"/)
	assert.match(editor, /production_order: "",/)
	assert.match(editor, /watch\(itemGroups, \(\) => syncProductionOrders\(\), \{ deep: true \}\)/)
	assert.match(editor, /syncItemProductionOrderRows\(form\.production_orders, productionOrderBaseline\.value, \[\.\.\.itemProductionOrders\(\), extra\]/)
})

function loadDeskScript() {
	const handlers = {}
	const calls = []
	const locals = {}
	const frappe = {
		ui: { form: { on: (doctype, events) => { (handlers[doctype] ||= []).push(events) } } },
		model: {
			set_value(cdt, cdn, fieldname, value) {
				locals[cdt][cdn][fieldname] = value
				for (const events of handlers[cdt]) events[fieldname]?.(context.frm, cdt, cdn)
			},
			clear_doc(cdt, cdn) {
				const row = locals[cdt][cdn]
				context.frm.doc[row.parentfield] = context.frm.doc[row.parentfield].filter((item) => item !== row)
			},
		},
		call(options) {
			calls.push(options)
			const message = options.method.endsWith("get_production_order_item_groups") ? ["Yarn"] : { item_name: `ITEM-${options.args?.production_order}` }
			options.callback?.({ message })
			return Promise.resolve({ message })
		},
		perm: { has_perm: () => false },
		user: { has_role: () => false },
	}
	const context = { frappe, locals, __: (text) => text, essdee_yrp: {}, console }
	vm.runInNewContext(source("../../essdee_yrp/public/js/purchase_order.js"), context)
	const run = (doctype, event, ...args) => { for (const events of handlers[doctype]) events[event]?.(context.frm, ...args) }
	return { context, run, calls, locals }
}

function deskForm(locals, { table = [], items = [], dirty = false, name = "PO-1" } = {}) {
	const child = (doctype, parentfield) => (values, index) => {
		const row = { doctype, parentfield, name: `${parentfield}-${index}`, ...values }
		;(locals[doctype] ||= {})[row.name] = row
		return row
	}
	const doc = {
		name, docstatus: 0,
		production_orders: table.map((production_order, index) => child("SD YRP Purchase Order Production Order", "production_orders")({ production_order, item_name: "OLD" }, index)),
		items: items.map(child("Purchase Order Item", "items")),
	}
	let added = 0
	return {
		doc, refreshed: [],
		is_dirty: () => dirty,
		is_new: () => false,
		set_query() {},
		refresh_field(fieldname) { this.refreshed.push(fieldname) },
		add_child(fieldname, values) {
			const row = child("SD YRP Purchase Order Production Order", fieldname)(values, `new-${added++}`)
			doc[fieldname].push(row)
			return row
		},
	}
}

test("Desk row PPO joins the table live, keeps saved rows and undoes its own unsaved addition", async () => {
	const { context, run, locals } = loadDeskScript()
	context.frm = deskForm(locals, { table: ["PPO-4"], items: [{ item_code: "YARN-1", item_group: "Yarn" }] })
	run("Purchase Order", "refresh")
	await new Promise((resolve) => setImmediate(resolve))
	assert.deepEqual(context.frm.doc.__onload.production_order_item_groups, ["Yarn"])
	const row = context.frm.doc.items[0]
	context.frappe.model.set_value(row.doctype, row.name, "production_order", "PPO-1")
	assert.deepEqual(names(context.frm.doc.production_orders), ["PPO-4", "PPO-1"])
	assert.equal(context.frm.doc.production_orders[1].item_name, "ITEM-PPO-1")
	context.frappe.model.set_value(row.doctype, row.name, "production_order", "PPO-2")
	assert.deepEqual(names(context.frm.doc.production_orders), ["PPO-4", "PPO-2"])
	context.frappe.model.set_value(row.doctype, row.name, "production_order", "")
	assert.deepEqual(names(context.frm.doc.production_orders), ["PPO-4"])
	assert.ok(context.frm.refreshed.includes("production_orders"))
})

test("Desk changing the item clears the row PPO; the field shows only for approval Item Groups", () => {
	const { context, run, locals } = loadDeskScript()
	context.frm = deskForm(locals, { items: [{ item_code: "YARN-1", item_group: "Yarn", production_order: "PPO-1" }] })
	run("Purchase Order", "refresh")
	const row = context.frm.doc.items[0]
	context.frappe.model.set_value(row.doctype, row.name, "item_code", "BUTTON-1")
	assert.equal(row.production_order, "")
	const fixture = JSON.parse(source("../../essdee_yrp/fixtures/custom_field.json")).find((field) => field.name === "Purchase Order Item-production_order")
	const visible = (item_group, onload) => vm.runInNewContext(fixture.depends_on.slice(5), { doc: { item_group }, parent: { __onload: onload } })
	assert.equal(visible("Yarn", { production_order_item_groups: ["Yarn"] }), true)
	assert.equal(visible("Buttons", { production_order_item_groups: ["Yarn"] }), false)
	assert.equal(visible("Yarn", undefined), false)
	assert.equal(fixture.reqd, 0)
})

test("/web PPO search sends the entry Lot so a linked Lot limits the list", async () => {
	const editor = source("../src/departments/fabric-store/PurchaseOrderEditor.vue")
	assert.match(editor, /<template #entry-fields="\{ values, schema, dimensions \}">/)
	assert.match(editor, /:search-handler="\(query\) => searchPurchaseOrderProductionOrders\(query, dimensions\?\.lot\)"/)
	assert.match(source("../src/components/stock/StockItemComposer.vue"), /<slot name="entry-fields" :values="entryValues" :schema="itemSchema" :dimensions="dimensionValues"/)
	const api = source("../src/api/fabricStore.js").match(/export function searchPurchaseOrderProductionOrders[\s\S]*?\n\}/)?.[0]
	const sent = []
	new Function("callRead", `${api.replace("export ", "")}\nreturn searchPurchaseOrderProductionOrders`)((method, args) => sent.push([method, args]))("TEE", "LOT-A")
	assert.deepEqual(sent, [["essdee_yrp.purchase_order_against.search_production_orders", { txt: "TEE", lot: "LOT-A" }]])
})

test("Desk row PPO query passes the row Lot", () => {
	const { context, run, locals } = loadDeskScript()
	const queries = {}
	context.frm = deskForm(locals, { items: [{ item_code: "YARN-1", item_group: "Yarn", lot: "LOT-A" }, { item_code: "YARN-2", item_group: "Yarn" }] })
	context.frm.set_query = (fieldname, table, query) => { queries[`${table}.${fieldname}`] = query }
	run("Purchase Order", "setup")
	const [withLot, withoutLot] = context.frm.doc.items
	const query = queries["items.production_order"]
	assert.deepEqual(JSON.parse(JSON.stringify(query(context.frm.doc, withLot.doctype, withLot.name))), { query: "essdee_yrp.purchase_order_against.production_order_query", filters: { lot: "LOT-A" } })
	assert.deepEqual(JSON.parse(JSON.stringify(query(context.frm.doc, withoutLot.doctype, withoutLot.name))), { query: "essdee_yrp.purchase_order_against.production_order_query", filters: { lot: "" } })
})
