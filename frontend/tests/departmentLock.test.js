import assert from "node:assert/strict"
import { readFileSync, readdirSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"
import { ACCOUNTS_ROUTES } from "../src/departments/accounts/accountsViews.js"

import { departments, getWorkspacePaths } from "../src/departments/registry.js"
import { MERCH_PD_ROUTES } from "../src/departments/merch-pd/merchPdRoutes.js"
import { MERCH_PURCHASE_ROUTES } from "../src/departments/merch-purchase/merchPurchaseRoutes.js"
import { QUALITY_ROUTES } from "../src/departments/quality/qualityRoutes.js"
import { MERCH_ROUTES } from "../src/departments/merch/merchViews.js"
import { PD_ROUTES } from "../src/departments/pd/pdViews.js"
import { PLANNING_ROUTES } from "../src/departments/planning/planningViews.js"
import { PURCHASE_ROUTES } from "../src/departments/purchase/purchaseViews.js"
import {
	getHomePath,
	getLockedDepartment,
	getLockedRedirect,
	getWorkspaceHomeRedirect,
	isLockedExit,
	isOutsideLayout,
	isWorkspaceInLayout,
	LAYOUT_UNAVAILABLE_PATH,
	WORKSPACE_HOME_PATH,
} from "../src/router/departmentLock.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const boot = (meta, config = {}) => ({ ui_config: { config, meta } })
const registered = (key, workspaces) => boot(
	{ render_mode: "Registered Experience", experience_key: key },
	workspaces ? { experience_props: { workspaces } } : {},
)
const route = (path, params = {}) => ({ path, fullPath: path, params })
const notInLayout = (from) => ({ path: LAYOUT_UNAVAILABLE_PATH, query: { from }, replace: true })

const sales = getLockedDepartment(registered("sales", ["production_orders", "reports"]))
const cutting = getLockedDepartment(registered("cutting", ["cutting-plans", "reports"]))

test("only a Registered Experience layout locks /web to a department", () => {
	assert.equal(getLockedDepartment(undefined), null)
	assert.equal(getLockedDepartment({}), null)
	assert.equal(getLockedDepartment(boot({ render_mode: "Configurable Layout", experience_key: "cutting" })), null)
	assert.equal(sales.path, "/sales")
	assert.deepEqual(sales.workspaces, ["production_orders", "reports"])
	assert.deepEqual(getLockedDepartment(registered("hr")).workspaces, ["bill_tracking", "reports"])
	assert.equal(getHomePath(sales), "/sales")
	assert.equal(getHomePath(null), "/")
})

test("an unknown experience keeps the permission-based view and warns", (t) => {
	const warn = t.mock.method(console, "warn", () => {})
	assert.equal(getLockedDepartment(registered("unknown-desk")), null)
	assert.equal(warn.mock.callCount(), 1)
	assert.match(warn.mock.calls[0].arguments[0], /unknown-desk/)
})

test("without a layout every route stays open", () => {
	for (const path of ["/", "/cutting", "/sales/reports", "/cutting/plans"]) {
		assert.equal(getLockedRedirect(route(path), null), undefined)
		assert.equal(isOutsideLayout(path, null), false)
	}
	assert.equal(isLockedExit("/", null), false)
})

test("the workspaces page opens the layout's department", () => {
	assert.deepEqual(getLockedRedirect(route("/"), sales), { path: "/sales", replace: true })
})

test("other departments show the not-in-your-layout page", () => {
	for (const path of ["/cutting", "/cutting/", "/CUTTING", "/cutting/plans", "/merch/lots", "/hr/reports"]) {
		assert.deepEqual(getLockedRedirect(route(path), sales), notInLayout(path))
	}
})

test("sections outside the layout are hidden; listed sections and sub-flows stay open", () => {
	for (const path of ["/cutting", "/cutting/plans", "/cutting/plans/new", "/cutting/reports"]) {
		assert.equal(getLockedRedirect(route(path), cutting), undefined)
	}
	for (const path of ["/cutting/orders", "/cutting/bulk-lay-sheets", "/cutting/lay-sheet-planner/new"]) {
		assert.deepEqual(getLockedRedirect(route(path), cutting), notInLayout(path))
	}
	const sewingReports = getLockedDepartment(registered("sewing", ["reports"]))
	const sewingOrders = getLockedDepartment(registered("sewing", ["work_orders"]))
	const storeReports = getLockedDepartment(registered("fabric-store", ["reports"]))
	const storePurchases = getLockedDepartment(registered("fabric-store", ["purchase_orders"]))
	assert.deepEqual(getLockedRedirect(route("/sewing/delivery-challans/new"), sewingReports), notInLayout("/sewing/delivery-challans/new"))
	assert.equal(getLockedRedirect(route("/sewing/delivery-challans/new"), sewingOrders), undefined)
	assert.deepEqual(getLockedRedirect(route("/fabric-store/goods-received-notes/new"), storeReports), notInLayout("/fabric-store/goods-received-notes/new"))
	assert.equal(getLockedRedirect(route("/fabric-store/goods-received-notes/new"), storePurchases), undefined)
	assert.deepEqual(getLockedRedirect(route("/sales/unknown"), sales), notInLayout("/sales/unknown"))
	assert.equal(getLockedRedirect(route("/sales/production-orders"), sales), undefined)
	assert.equal(getLockedRedirect(route(LAYOUT_UNAVAILABLE_PATH), sales), undefined)
	assert.equal(getLockedRedirect(route("/document-unavailable", { pathMatch: ["document-unavailable"] }), sales), undefined)
})

test("document pages linked from the layout stay open", () => {
	assert.equal(getLockedRedirect(route("/merch/lots/LOT-1", { lotId: "LOT-1" }), sales), undefined)
	assert.equal(getLockedRedirect(route("/cutting/orders/CO-1", { cuttingOrderId: "CO-1" }), cutting), undefined)
})

test("launcher cards and back links follow the layout", () => {
	assert.equal(isWorkspaceInLayout({ key: "reports", to: "/cutting/reports" }, cutting), true)
	assert.equal(isWorkspaceInLayout({ key: "orders", to: "/cutting/orders" }, cutting), false)
	assert.equal(isWorkspaceInLayout({ key: "plans", to: { path: "/sewing/plans", query: {} } }, cutting), false)
	assert.equal(isWorkspaceInLayout({ key: "plans", to: { path: "/sewing/plans" } }, null), true)
	assert.equal(isLockedExit("/", sales), true)
	assert.equal(isLockedExit("/merch", sales), true)
	assert.equal(isLockedExit("/sales", sales), false)
	assert.equal(isLockedExit("/sales/production-orders", sales), false)
})

test("registry sections match real routes", () => {
	const viewSources = readdirSync(new URL("../src/departments/", import.meta.url), { recursive: true })
		.filter((path) => /Views\.js$/.test(path))
		.map((path) => source(`../src/departments/${path}`))
	const routeSources = [source("../src/router/index.js"), ...viewSources].join("\n")
	for (const department of departments) {
		const owned = new Set(Object.values(getWorkspacePaths(department)).flat())
		for (const path of owned) {
			assert.ok(routeSources.includes(`"${path}`) || routeSources.includes(`\`${path}`), path)
		}
		const routed = [...routeSources.matchAll(new RegExp(`["\`]${department.path}/([a-z-]+)`, "g"))].map((match) => match[1])
		for (const segment of routed) assert.ok(owned.has(`${department.path}/${segment}`), `${department.path}/${segment} has no owning workspace`)
	}
})

test("the real route table decides which pages are documents", () => {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, MERCH_PD_ROUTES, MERCH_PURCHASE_ROUTES, QUALITY_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH: "/no-permission" }
	vm.runInNewContext(routerSource, context)
	const guard = (path, department) => getLockedRedirect(context.router.resolve(path), department)
	const sewingReports = getLockedDepartment(registered("sewing", ["reports"]))

	assert.equal(guard("/merch/lots/LOT%2F1", sales), undefined)
	assert.equal(guard("/sales/production-orders/PPO-1/edit", sales), undefined)
	assert.equal(guard("/cutting/CP-1", sales), undefined)
	assert.equal(guard("/cutting/plans/CP-1", sales), undefined)
	assert.equal(guard("/accounts/debits/D-1", sales), undefined)
	assert.equal(guard(LAYOUT_UNAVAILABLE_PATH, sales), undefined)
	assert.deepEqual(guard("/sales/production-orders/new", cutting), notInLayout("/sales/production-orders/new"))
	assert.deepEqual(guard("/sewing/delivery-challans/new", sewingReports), notInLayout("/sewing/delivery-challans/new"))
	assert.deepEqual(guard("/accounts/debits", sales), notInLayout("/accounts/debits"))
	assert.deepEqual(guard("/cutting", sales), notInLayout("/cutting"))
	assert.deepEqual(guard("/", sales), { path: "/sales", replace: true })
})

const workspaceBoot = boot(
	{ render_mode: "Registered Experience", experience_key: "workspace", department_layout: "Floor Desk" },
	{ experience_props: { workspace: { title: "Floor Desk", sections: [
		{ label: "Orders", cards: ["merch:lots", "planning:lots", "removed:card"] },
		{ label: "Buying", cards: ["purchase:purchase_orders"] },
	] } } },
)
const workspace = getLockedDepartment(workspaceBoot)

test("a workspace layout locks /web to its own home with its sections of catalogue cards", () => {
	assert.equal(workspace.key, "workspace")
	assert.equal(workspace.label, "Floor Desk")
	assert.equal(getHomePath(workspace), WORKSPACE_HOME_PATH)
	assert.deepEqual(workspace.sections.map((section) => section.label), ["Orders", "Buying"])
	assert.deepEqual(workspace.sections[0].cards, ["merch:lots", "planning:lots"])
	assert.deepEqual(workspace.paths, ["/merch/lots", "/planning/lots", "/purchase/purchase-orders"])
})

test("a workspace layout opens its card pages and below, and sends landings home", () => {
	for (const path of ["/merch/lots", "/merch/lots/new", "/planning/lots", "/purchase/purchase-orders", WORKSPACE_HOME_PATH, "/no-permission"]) {
		assert.equal(getLockedRedirect(route(path), workspace), undefined, path)
	}
	for (const path of ["/", "/merch", "/cutting", "/purchase/"]) {
		assert.deepEqual(getLockedRedirect(route(path), workspace), { path: WORKSPACE_HOME_PATH, replace: true }, path)
	}
	for (const path of ["/merch/production-orders", "/planning/cutting-plans", "/cutting/plans", "/merch/lotsx"]) {
		assert.deepEqual(getLockedRedirect(route(path), workspace), notInLayout(path), path)
	}
	assert.equal(getLockedRedirect(route("/cutting/plans/CP-1", { planId: "CP-1" }), workspace), undefined)
	assert.equal(isWorkspaceInLayout({ to: "/merch/lots" }, workspace), true)
	assert.equal(isWorkspaceInLayout({ to: "/merch/item-production-details" }, workspace), false)
	assert.equal(isOutsideLayout("/merch", workspace), false)
	assert.equal(isOutsideLayout("/cutting", workspace), true)
	assert.equal(isLockedExit("/", workspace), true)
	assert.equal(isLockedExit("/merch", workspace), false)
	assert.equal(isLockedExit("/merch/lots", workspace), false)
	assert.equal(isLockedExit(WORKSPACE_HOME_PATH, workspace), false)
})

test("a workspace layout without sections still locks to an empty home", () => {
	const empty = getLockedDepartment(boot({ render_mode: "Registered Experience", experience_key: "workspace", department_layout: "Empty" }))
	assert.equal(empty.label, "Empty")
	assert.deepEqual(empty.sections, [])
	assert.deepEqual(getLockedRedirect(route("/merch/lots"), empty), notInLayout("/merch/lots"))
})

test("only a workspace layout opens the workspace home", () => {
	assert.equal(getWorkspaceHomeRedirect(workspace), undefined)
	assert.deepEqual(getWorkspaceHomeRedirect(sales), { path: "/sales", replace: true })
	assert.deepEqual(getWorkspaceHomeRedirect(null), { path: "/", replace: true })
})

const plannerSections = [{ label: "Cutting", cards: ["planning:cutting_plans"] }, { label: "Borrowed", cards: ["merch:lots", "removed:card"] }]
const plannerBoot = (layout) => ({ ui_config: {
	meta: { render_mode: "Registered Experience", experience_key: "planning", department_layout: layout },
	config: { experience_props: { workspaces: ["dashboard", "lots"] } },
	department_workspaces: { planning: { layout: "Production Planner", sections: plannerSections } },
} })

test("an overridden department layout locks to its landing with the saved cards, borrowed ones included", () => {
	const planner = getLockedDepartment(plannerBoot("Production Planner"))
	assert.equal(planner.key, "planning")
	assert.equal(getHomePath(planner), "/planning")
	assert.deepEqual(planner.sections, [{ label: "Cutting", cards: ["planning:cutting_plans"] }, { label: "Borrowed", cards: ["merch:lots"] }])
	for (const path of ["/planning", "/planning/cutting-plans", "/planning/cutting-plans/new", "/merch/lots"]) {
		assert.equal(getLockedRedirect(route(path), planner), undefined, path)
	}
	for (const path of ["/", "/merch"]) assert.deepEqual(getLockedRedirect(route(path), planner), { path: "/planning", replace: true }, path)
	for (const path of ["/planning/dashboard", "/planning/lots", "/merch/item-production-details"]) {
		assert.deepEqual(getLockedRedirect(route(path), planner), notInLayout(path), path)
	}
	assert.deepEqual(getWorkspaceHomeRedirect(planner), { path: "/planning", replace: true })
	assert.equal(isLockedExit("/planning", planner), false)
})

test("another layout of the same department keeps its own workspaces", () => {
	const other = getLockedDepartment(plannerBoot("Planner Lite"))
	assert.deepEqual(other.workspaces, ["dashboard", "lots"])
	assert.equal(getLockedRedirect(route("/planning/dashboard"), other), undefined)
	assert.deepEqual(getLockedRedirect(route("/merch/lots"), other), notInLayout("/merch/lots"))
})
