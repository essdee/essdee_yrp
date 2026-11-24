import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import { getSelectedCardKey, workspaceCardsSinkKey } from "../src/components/navigation/moduleSidebar.js"

const CARDS = [
	{ key: "cutting_plans", label: "Cutting Plan", icon: "pi pi-th-large", to: "/planning/cutting-plans" },
	{ key: "lots", label: "Lot", icon: "pi pi-inbox", to: "/planning/lots" },
	{ key: "lot_reports", label: "Lot Reports", icon: "pi pi-chart-bar", to: "/planning/lots-reports" },
]

test("the selected card is the longest card path owning the route", () => {
	assert.equal(getSelectedCardKey(CARDS, "/planning/lots"), "lots")
	assert.equal(getSelectedCardKey(CARDS, "/planning/lots/LOT-001"), "lots")
	assert.equal(getSelectedCardKey(CARDS, "/planning/lots-reports"), "lot_reports")
	assert.equal(getSelectedCardKey(CARDS, "/planning"), "")
	assert.equal(getSelectedCardKey([{ key: "q", to: "/a/b?x=1" }], "/a/b/c"), "q")
})

test("a launcher under the module sidebar reports its permitted cards and renders nothing", async () => {
	const stub = (name) => (props, { slots }) => Vue.h(name, props, slots.default?.())
	const component = loadComponent(new URL("../src/components/common/WorkspaceLauncher.vue", import.meta.url).pathname, {
		"primevue/skeleton": stub("skeleton"),
		"vue-router": { RouterLink: stub("router-link") },
		"../../router/departmentLock.js": { isWorkspaceInLayout: () => true },
		"../../router/listPermission.js": { canOpenList: (to) => to !== "/planning/lots-reports" },
		"../navigation/InlinePageNavigation.vue": stub("navigation"),
		"./WorkspaceSearch.vue": stub("workspace-search"),
		"../navigation/moduleSidebar.js": { workspaceCardsSinkKey },
	})
	const reported = []
	const props = Vue.reactive({ title: "Planning", items: CARDS, loading: true })
	const host = { setup: () => { Vue.provide(workspaceCardsSinkKey, (items) => reported.push(items.map((item) => item.key))) }, render: () => Vue.h(component, props) }
	const root = mountComponent(host, {})
	try {
		assert.deepEqual(reported, [[]])
		props.loading = false
		await Vue.nextTick()
		assert.deepEqual(reported.at(-1), ["cutting_plans", "lots"])
		assert.equal(findNodes(root, (node) => node.type === "router-link" || node.type === "section").length, 0)
	} finally { root.__vue_app__.unmount() }
})

test("tablets and phones open the module sidebar as a drawer from the top bar", async () => {
	const { readFileSync } = await import("node:fs")
	const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
	const { DRAWER_MEDIA_QUERY } = await import("../src/components/navigation/moduleSidebar.js")
	assert.equal(DRAWER_MEDIA_QUERY, "(max-width: 900px), (hover: none)")
	const app = read("../src/App.vue")
	assert.match(app, /<ModuleSidebar ref="moduleSidebar" v-model:open="isModuleNavigationOpen"[^>]*@availability="hasModuleNavigation = \$event"/)
	assert.match(app, /@click="moduleSidebar\?\.toggle\(\)"/)
	assert.match(app, /v-if="hasModuleNavigation"[\s\S]*?class="app-theme-toggle app-nav-toggle"[\s\S]*?aria-controls="module-sidebar"/)
	assert.match(app, /isModuleNavigationOpen\.value = false/)
	const sidebar = read("../src/components/navigation/ModuleSidebar.vue")
	assert.match(sidebar, /:pinned="isDrawer \|\| isPinned"/)
	assert.match(sidebar, /if \(isDrawer\.value\) return emit\("update:open", !props\.open\)/)
	assert.match(sidebar, /saveSidebarPinned\(user, isPinned\.value\)/)
	assert.match(sidebar, /@media \(max-width: 900px\), \(hover: none\) \{\n\t\.module-sidebar \{ display: none; \}\n\t\.module-sidebar\.is-open \{/)
	assert.match(sidebar, /event\.key === "Escape" && isDrawerOpen\.value/)
})

test("a launcher drawing Layout Builder sections reports their cards to the module sidebar, grouped by section", async () => {
	const stub = (name) => (props, { slots }) => Vue.h(name, props, slots.default?.())
	const component = loadComponent(new URL("../src/components/common/WorkspaceLauncher.vue", import.meta.url).pathname, {
		"primevue/skeleton": stub("skeleton"),
		"vue-router": { RouterLink: stub("router-link") },
		"../../router/departmentLock.js": { isWorkspaceInLayout: () => true },
		"../../router/listPermission.js": { canOpenList: (to) => to !== "/cutting/reports" },
		"../navigation/InlinePageNavigation.vue": stub("navigation"),
		"./WorkspaceSearch.vue": stub("workspace-search"),
		"../navigation/moduleSidebar.js": { workspaceCardsSinkKey },
	})
	const sections = [
		{ label: "Plans", items: [{ key: "cutting:cutting-plans", label: "Cutting Plan", to: "/cutting/plans" }, { key: "cutting:reports", label: "Reports", to: "/cutting/reports" }] },
		{ label: "Orders", items: [{ key: "cutting:cutting-orders", label: "Cutting Order", to: "/cutting/orders" }] },
	]
	const reported = []
	const props = Vue.reactive({ title: "Cutting", sections, loading: true })
	const host = { setup: () => { Vue.provide(workspaceCardsSinkKey, (items) => reported.push(items.map((item) => [item.key, item.group]))) }, render: () => Vue.h(component, props) }
	const root = mountComponent(host, {})
	try {
		assert.deepEqual(reported, [[]])
		props.loading = false
		await Vue.nextTick()
		assert.deepEqual(reported.at(-1), [["cutting:cutting-plans", "Plans"], ["cutting:cutting-orders", "Orders"]])
	} finally { root.__vue_app__.unmount() }
})

test("the desktop sidebar's open state is remembered per user and survives unavailable storage", async () => {
	const { isSidebarPinned, saveSidebarPinned } = await import("../src/components/navigation/moduleSidebar.js")
	const values = new Map()
	const storage = { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) }
	assert.equal(isSidebarPinned("a@example.com", storage), false)
	saveSidebarPinned("a@example.com", true, storage)
	assert.equal(isSidebarPinned("a@example.com", storage), true)
	assert.equal(isSidebarPinned("b@example.com", storage), false)
	saveSidebarPinned("a@example.com", false, storage)
	assert.equal(isSidebarPinned("a@example.com", storage), false)
	const blocked = { getItem: () => { throw new Error("blocked") }, setItem: () => { throw new Error("blocked") } }
	assert.equal(isSidebarPinned("a@example.com", blocked), false)
	assert.doesNotThrow(() => saveSidebarPinned("a@example.com", true, blocked))
})
