import assert from "node:assert/strict"
import test from "node:test"

test("a phone list card shows the status beside the name and keeps it out of the facts", async () => {
	const { Vue, findNodes, loadComponent, mountComponent } = await import("../../scripts/helpers/vue_renderer.mjs")
	globalThis.Document ??= class Document {}
	globalThis.ShadowRoot ??= class ShadowRoot {}
	const previousWindow = globalThis.window
	globalThis.window = { sessionStorage: { getItem: () => null }, frappe: {} }
	const fields = [{ fieldname: "lot", fieldtype: "Data", label: "Lot", in_list_view: 1 }, { fieldname: "status", fieldtype: "Select", label: "Status", in_list_view: 1 }]
	const stub = (name) => (props) => Vue.h(name, props)
	const modules = {
		"vue-router": { useRoute: () => ({ fullPath: "/list" }) },
		"../../api/frappe.js": {
			getMeta: async () => [{ name: "Entry", fields }],
			getActiveWorkflow: async () => null,
			getUserListview: async () => ({ fields: [{ fieldname: "name" }, ...fields], columns: null }),
			getItemFilterValues: async () => ({}),
			getList: async () => [{ name: "ENTRY-1", lot: "LOT-9", status: "Planned" }],
			getCount: async () => 1,
			getCounts: async (doctype, filterSets) => filterSets.map(() => 1),
		},
		"./listColumns.js": await import("../src/components/common/listColumns.js"),
		"../../utils/listNavigation.js": await import("../src/utils/listNavigation.js"),
		"../../utils/statusTone.js": await import("../src/utils/statusTone.js"),
		"../../utils/prettyDate.js": await import("../src/utils/prettyDate.js"),
		"./listStatusFilters.js": await import("../src/components/common/listStatusFilters.js"),
		"./listItemFilters.js": await import("../src/components/common/listItemFilters.js"),
	}
	for (const name of ["button", "column", "datatable", "dialog", "inputtext", "menu", "message", "paginator", "select"]) modules[`primevue/${name}`] = stub(name)
	for (const path of ["../documents/DocumentStatusBadge.vue", "../navigation/InlinePageNavigation.vue", "./ListviewQuickFilters.vue"]) modules[path] = stub(path)
	modules["./asyncListParts.js"] = { FormField: stub("./FormField.vue"), UserListviewColumns: stub("./UserListviewColumns.vue"), ListviewFilters: stub("./ListviewFilters.vue") }
	const tick = async () => { await new Promise((resolve) => setImmediate(resolve)); await Vue.nextTick() }
	const text = (node) => node.text || node.children.map(text).join("")
	let root
	try {
		root = mountComponent(loadComponent("frontend/src/components/common/ListView.vue", modules), Vue.reactive({ doctype: "Entry", navigationEnabled: false }))
		await tick(); await tick()
		const [title] = findNodes(root, (node) => node.props?.class === "mobile-list-record__title")
		assert.match(text(title), /ENTRY-1/)
		const [badge] = findNodes(title, (node) => node.type === "../documents/DocumentStatusBadge.vue")
		assert.equal(badge.props.label, "Planned")
		const [facts] = findNodes(root, (node) => node.props?.class === "mobile-list-record__facts")
		assert.match(text(facts), /Lot\s*LOT-9/)
		assert.doesNotMatch(text(facts), /Planned|Status/)
	} finally {
		globalThis.window = previousWindow
		root?.unmount?.()
	}
})
