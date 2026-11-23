import assert from "node:assert/strict"
import { resolve } from "node:path"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const { linkedDocumentGroups } = await import("../src/utils/linkedDocuments.js")
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const text = (root) => findNodes(root, (node) => node.text).map((node) => node.text).join(" ")

test("linked documents are grouped by doctype with docstatus labels and /web or Desk targets", () => {
	const groups = linkedDocumentGroups({
		"YRP Delivery Challan": { docs: [{ name: "DC-1", docstatus: 1 }, { name: "DC-2", docstatus: 2 }], hidden_count: 0 },
		"YRP Unknown Doc": { docs: [{ name: "U 1", docstatus: 0 }], hidden_count: 2 },
		"YRP Restricted": { docs: [], hidden_count: 3 },
		"YRP Empty": { docs: [], hidden_count: 0 },
	}, "/web/fabric-store/work-orders/WO-1")
	assert.deepEqual(groups.map((group) => [group.doctype, group.hiddenCount]), [["YRP Delivery Challan", 0], ["YRP Unknown Doc", 2], ["YRP Restricted", 3]])
	assert.deepEqual(groups[0].rows, [
		{ name: "DC-1", status: "Submitted", docstatus: 1, href: "/web/fabric-store/delivery-challans/DC-1", route: "/fabric-store/delivery-challans/DC-1" },
		{ name: "DC-2", status: "Cancelled", docstatus: 2, href: "/web/fabric-store/delivery-challans/DC-2", route: "/fabric-store/delivery-challans/DC-2" },
	])
	assert.deepEqual(groups[1].rows[0], { name: "U 1", status: "Draft", docstatus: 0, href: "/desk/yrp-unknown-doc/U%201", route: null })
	assert.deepEqual(linkedDocumentGroups({}, "/web"), [])
	assert.deepEqual(linkedDocumentGroups(null, "/web"), [])
})

function loadStrip() {
	return loadComponent(resolve("frontend/src/components/documents/DocumentActionStrip.vue"), {
		"primevue/button": (props) => Vue.h("button", props, props.label),
		"primevue/menu": Vue.defineComponent({ props: ["model"], setup(props, { expose }) { expose({ toggle() {} }); return () => Vue.h("menu", { model: props.model }) } }),
		"./LinkedDocumentsDialog.vue": (props) => Vue.h("linked-dialog", props),
	})
}

test("DocumentActionStrip adds a menu-only Show Links for a saved document", async () => {
	const strip = loadStrip()
	const props = Vue.reactive({ actions: [{ key: "save", label: "Save", primary: true, command() {} }], doctype: "YRP Work Order", docname: "WO-1" })
	const root = mountComponent(strip, props)
	const more = findNodes(root, (node) => node.type === "button" && node.props.label === "More")
	assert.equal(more.length, 2, "desktop and mobile More buttons")
	more[0].props.onClick({})
	await tick()
	const menu = findNodes(root, (node) => node.type === "menu")[0]
	const item = menu.props.model.find((entry) => entry.label === "Show Links")
	assert.ok(item, "More menu lists Show Links")
	const dialog = () => findNodes(root, (node) => node.type === "linked-dialog")[0]
	assert.deepEqual([dialog().props.doctype, dialog().props.docname, dialog().props.visible], ["YRP Work Order", "WO-1", false])
	item.command()
	await tick()
	assert.equal(dialog().props.visible, true)
})

test("DocumentActionStrip has no Show Links without a doctype or for an unsaved document", async () => {
	const strip = loadStrip()
	for (const props of [{ actions: [] }, { actions: [], doctype: "YRP Work Order", docname: "" }]) {
		const root = mountComponent(strip, props)
		assert.equal(findNodes(root, (node) => node.type === "button").length, 0)
		assert.equal(findNodes(root, (node) => node.type === "linked-dialog").length, 0)
	}
	const root = mountComponent(strip, { actions: [], doctype: "SD YRP Lot", docname: "LOT-1" })
	assert.equal(findNodes(root, (node) => node.type === "button" && node.props.label === "More").length, 2, "Show Links alone still opens a More menu")
})

function loadDialog(linked, pushes, calls = []) {
	return loadComponent(resolve("frontend/src/components/documents/LinkedDocumentsDialog.vue"), {
		"primevue/dialog": (props, { slots }) => Vue.h("dialog", props, props.visible ? slots.default?.() : []),
		"vue-router": { useRouter: () => ({ push: async (target) => pushes.push(target) }) },
		"../../api/frappe.js": { getLinkedDocuments: async (...args) => { calls.push(args); return linked } },
		"./DocumentStatusBadge.vue": (props) => Vue.h("status-badge", props, props.label),
		"../../utils/linkedDocuments.js": { linkedDocumentGroups },
	})
}

test("LinkedDocumentsDialog loads links when opened, groups them and opens the /web page", async () => {
	const pushes = [], calls = []
	const linked = {
		"YRP Goods Received Note": { docs: [{ name: "GRN-1", docstatus: 1 }], hidden_count: 1 },
		"YRP Unknown Doc": { docs: [{ name: "U-1", docstatus: 0 }], hidden_count: 0 },
	}
	const props = Vue.reactive({ doctype: "YRP Work Order", docname: "WO-1", visible: false, "onUpdate:visible": (value) => { props.visible = value } })
	const root = mountComponent(loadDialog(linked, pushes, calls), props)
	await tick()
	assert.deepEqual(calls, [], "nothing loads until the dialog opens")
	props.visible = true
	await tick(); await tick()
	assert.deepEqual(calls, [["YRP Work Order", "WO-1"]])
	const content = text(root)
	for (const expected of ["YRP Goods Received Note", "GRN-1", "Submitted", "1 restricted document", "YRP Unknown Doc", "U-1", "Draft"]) assert.match(content, new RegExp(expected))
	const links = findNodes(root, (node) => node.type === "a")
	assert.deepEqual(links.map((link) => link.props.href), ["/web/fabric-store/goods-received-notes/GRN-1", "/desk/yrp-unknown-doc/U-1"])
	let prevented = false
	links[0].props.onClick({ preventDefault: () => { prevented = true }, ctrlKey: false, metaKey: false, shiftKey: false, button: 0 })
	await tick()
	assert.equal(prevented, true)
	assert.deepEqual(pushes, ["/fabric-store/goods-received-notes/GRN-1"])
	assert.equal(props.visible, false, "opening a document closes the dialog")
	let desk = false
	links[1].props.onClick({ preventDefault: () => { desk = true }, button: 0 })
	assert.equal(desk, false, "Desk links use plain navigation")
})

test("LinkedDocumentsDialog shows the empty state", async () => {
	const root = mountComponent(loadDialog({}, []), { doctype: "YRP Work Order", docname: "WO-1", visible: true })
	await tick(); await tick()
	assert.match(text(root), /No linked documents/)
})

test("every document page passes its doctype and name to the More menu", async () => {
	const { readFileSync } = await import("node:fs")
	const pages = {
		"FabricWorkOrder.vue": "YRP Work Order", "FabricPurchaseOrder.vue": "Purchase Order", "CuttingOrder.vue": "SD YRP Cutting Order", "CuttingPlan.vue": "SD YRP Cutting Plan",
		"fabric-store/DeliveryChallanWorkspace.vue": "YRP Delivery Challan", "fabric-store/GoodsReceivedNoteWorkspace.vue": "YRP Goods Received Note",
		"sales/ProductionOrder.vue": "YRP Production Order", "merch/process-cost/ProcessCostPage.vue": "YRP Process Cost", "purchase/ItemPricePage.vue": "YRP Item Price",
		"purchase/ItemPage.vue": "Item", "hr/BillTracking.vue": "YRP Bill Tracking", "accounts/PurchaseInvoice.vue": "YRP Purchase Invoice",
		"pd/ProductReleasePage.vue": "SD YRP Product Release", "pd/components/ProductWorkspaceHeader.vue": "SD YRP Product", "pd/components/LotwiseWorkspaceHeader.vue": "SD YRP Lotwise Item Profit",
		"cut-panel-store/BoxStickerPrintPage.vue": "SD YRP Box Sticker Print", "merch/ipd/IpdPage.vue": "YRP Item Production Detail", "merch/ipd/IpdEditor.vue": "YRP Item Production Detail",
		...Object.fromEntries(["planning", "quality", "purchase"].flatMap((dept) => [[`${dept}/lot/LotPage.vue`, "SD YRP Lot"], [`${dept}/lot/LotEditor.vue`, "SD YRP Lot"]])),
		...Object.fromEntries(["merch", "merch-pd", "merch-purchase", "accounts"].flatMap((dept) => [[`${dept}/lot/MerchLotPage.vue`, "SD YRP Lot"], [`${dept}/lot/MerchLotEditor.vue`, "SD YRP Lot"]])),
	}
	for (const [path, doctype] of Object.entries(pages)) {
		const source = readFileSync(resolve(`frontend/src/departments/${path}`), "utf8")
		assert.match(source, new RegExp(`<DocumentActionStrip[^>]*doctype="${doctype}"[^>]*:docname="[^"]+"`), path)
	}
	assert.match(readFileSync(resolve("frontend/src/departments/quality/QualityInspection.vue"), "utf8"), /<DocumentActionStrip[^>]*:doctype="INSPECTION_DOCTYPE" :docname="record\.name \|\| ''"/)
	const headers = {
		"merch/supplier/SupplierPage.vue": ':doctype="SUPPLIER_DOCTYPE" :docname="supplierId"',
		"accounts/Debits.vue": 'doctype="YRP Debit" :docname="record.name"',
		"finishing/FinishingPlan.vue": 'doctype="SD YRP Finishing Plan" :docname="record.name || \'\'"',
		"finishing/FinishingDispatch.vue": 'doctype="SD YRP Finishing Plan Dispatch" :docname="record.name || \'\'"',
		"CuttingBulkLaySheet.vue": 'doctype="SD YRP Cutting Bulk Lay Sheets" :docname="record.name || \'\'"',
		"planning/action-master/ActionMasterPage.vue": ':doctype="doctype" :docname="doc.name || \'\'"',
	}
	for (const [path, binding] of Object.entries(headers)) {
		const source = readFileSync(resolve(`frontend/src/departments/${path}`), "utf8")
		assert.ok(source.includes(`<DocumentActionStrip ${binding} />`), path)
		assert.match(source, /import DocumentActionStrip from "[./]+\/components\/documents\/DocumentActionStrip\.vue"/, path)
	}
})
