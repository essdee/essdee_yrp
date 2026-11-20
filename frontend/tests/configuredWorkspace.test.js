import assert from "node:assert/strict"
import test from "node:test"

import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import { getReadableSections, getWorkspaceView } from "../src/departments/workspace/workspaceSections.js"
import { getLockedDepartment } from "../src/router/departmentLock.js"

const read = { can_read: true }
const ADMIN = { user: { name: "Administrator" } }
const lock = getLockedDepartment({ ui_config: {
	meta: { render_mode: "Registered Experience", experience_key: "workspace", department_layout: "Floor Desk" },
	config: { experience_props: { workspace: { title: "Floor Desk", sections: [
		{ label: "Orders", cards: ["merch:lots", "planning:lots", "merch:production_orders"] },
		{ label: "Buying", cards: ["purchase:purchase_orders"] },
	] } } },
} })

test("workspace sections keep only the cards the owner department grants", async () => {
	const all = { merch: { sections: { lots: read } }, planning: { sections: { lots: read } }, purchase: { sections: {} } }
	const sections = await getReadableSections(lock.sections, all, ADMIN)
	assert.deepEqual(sections.map((section) => section.label), ["Orders"])
	assert.deepEqual(sections[0].items.map((item) => [item.key, item.label, item.to]), [
		["merch:lots", "Lot", "/merch/lots"],
		["planning:lots", "Lot", "/planning/lots"],
	])
})

test("workspace sections drop cards whose list the user cannot read", async () => {
	const all = { merch: { sections: { lots: read } }, planning: { sections: { lots: read } }, purchase: { sections: { purchase_orders: read } } }
	const clerk = { user: { name: "clerk@example.com", can_read: ["Purchase Order"] } }
	const sections = await getReadableSections(lock.sections, all, clerk)
	assert.deepEqual(sections.map((section) => [section.label, section.items.map((item) => item.key)]), [["Buying", ["purchase:purchase_orders"]]])
})

test("the launcher draws one titled grid per section", async () => {
	const stub = (type) => (props) => Vue.h(type, props)
	const component = loadComponent(new URL("../src/components/common/WorkspaceLauncher.vue", import.meta.url).pathname, {
		"primevue/skeleton": stub("skeleton"),
		"vue-router": { RouterLink: stub("router-link") },
		"../../router/departmentLock.js": { isWorkspaceInLayout: () => true },
		"../../router/listPermission.js": { canOpenList: () => true },
		"../navigation/InlinePageNavigation.vue": stub("navigation"),
		"./WorkspaceSearch.vue": stub("workspace-search"),
		"../navigation/moduleSidebar.js": await import("../src/components/navigation/moduleSidebar.js"),
	})
	const sections = [
		{ label: "Orders", items: [{ key: "merch:lots", label: "Lot · Merch", to: "/merch/lots" }, { key: "planning:lots", label: "Lot · Planning", to: "/planning/lots" }] },
		{ label: "Buying", items: [{ key: "purchase:purchase_orders", label: "Purchase Orders · Purchase", to: "/purchase/purchase-orders" }] },
	]
	const root = mountComponent({ render: () => Vue.h(component, { title: "Floor Desk", sections }) }, {})
	const headings = findNodes(root, (node) => node.type === "h2").map((node) => node.text.trim())
	assert.deepEqual(headings, ["Orders", "Buying"])
	assert.deepEqual(findNodes(root, (node) => node.type === "router-link").map((node) => node.props.to), ["/merch/lots", "/planning/lots", "/purchase/purchase-orders"])
	assert.equal(findNodes(root, (node) => node.type === "workspace-search").length, 0)
})

test("an overridden department landing shows its saved sections; the workspace home shows the lock's", () => {
	const sections = [{ label: "Cutting", cards: ["planning:cutting_plans"] }, { label: "Sewing", cards: ["planning:sewing_plans", "merch:lots"] }]
	const boot = { ui_config: { department_workspaces: { planning: { layout: "Production Planner", sections } } } }
	assert.deepEqual(getWorkspaceView("/planning", null, boot), { title: "Planning", sections })
	assert.deepEqual(getWorkspaceView("/workspace", lock, boot), { title: "Floor Desk", sections: lock.sections })
	assert.deepEqual(getWorkspaceView("/merch", null, boot), { title: "Workspace", sections: [] })
})

test("every department landing switches to the saved sections when its layout is overridden", async () => {
	const { readFileSync } = await import("node:fs")
	const { departments } = await import("../src/departments/registry.js")
	const registry = readFileSync(new URL("../src/departments/registry.js", import.meta.url), "utf8")
	assert.deepEqual([...registry.matchAll(/component: landing\("([a-z-]+)"/g)].map((match) => match[1]), departments.map((department) => department.key))
	assert.match(registry, /getDepartmentWorkspace\(key\) \? import\("\.\/workspace\/ConfiguredWorkspace\.vue"\)/)
})
