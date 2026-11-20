import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"

import { ACCOUNTS_ROUTES } from "../src/departments/accounts/accountsViews.js"
import { MERCH_IPD_ROUTES, MERCH_ROUTES, ipdEditRoute, ipdRoute } from "../src/departments/merch/merchViews.js"
import { PD_ROUTES } from "../src/departments/pd/pdViews.js"
import { PLANNING_ROUTES, PLANNING_WORKSPACES, visiblePlanningWorkspaces } from "../src/departments/planning/planningViews.js"
import { PURCHASE_ROUTES } from "../src/departments/purchase/purchaseViews.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"
import { MERCH_PD_ROUTES } from "../src/departments/merch-pd/merchPdRoutes.js"
import { MERCH_PURCHASE_ROUTES } from "../src/departments/merch-purchase/merchPurchaseRoutes.js"
import { QUALITY_ROUTES } from "../src/departments/quality/qualityRoutes.js"
import { getLockedDepartment, getLockedRedirect, isWorkspaceInLayout, LAYOUT_UNAVAILABLE_PATH } from "../src/router/departmentLock.js"
import { canOpenList, NO_PERMISSION_PATH } from "../src/router/listPermission.js"
import { DEPARTMENT_RECORD_ROUTES } from "../src/router/webDocumentRoutes.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const PATH = "/planning/item-production-details"

function loadRouter() {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, MERCH_PD_ROUTES, MERCH_PURCHASE_ROUTES, QUALITY_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH }
	vm.runInNewContext(routerSource, context)
	return context.router
}

const props = (route) => {
	const value = route.matched.at(-1).props.default
	return JSON.parse(JSON.stringify(typeof value === "function" ? value(route) : value))
}

test("Planning shows the shared Item Production Detail card under its own path", () => {
	const card = PLANNING_WORKSPACES.find((item) => item.key === "item_production_details")
	assert.deepEqual([card.label, card.to], ["Item Production Detail", PATH])
	assert.deepEqual(visiblePlanningWorkspaces({ item_production_details: { can_read: true } }).map((item) => item.key), ["item_production_details"])
	assert.deepEqual(visiblePlanningWorkspaces({ item_production_details: { can_read: false } }), [])
	assert.deepEqual(getWorkspacePaths(departments.find((item) => item.key === "planning")).item_production_details, [PATH])
})

test("Planning IPD list, new, view and edit routes reuse the Merch IPD pages with Planning route names", () => {
	const router = loadRouter()
	const planning = { department: "Planning", departmentPath: "/planning", listPath: PATH, list: PLANNING_ROUTES.ipds, new: PLANNING_ROUTES.ipdNew, view: PLANNING_ROUTES.ipd, edit: PLANNING_ROUTES.ipdEdit }
	for (const [path, name, extra] of [[PATH, PLANNING_ROUTES.ipds, {}], [`${PATH}/new`, PLANNING_ROUTES.ipdNew, {}], [`${PATH}/IPD-1`, PLANNING_ROUTES.ipd, { ipdId: "IPD-1" }], [`${PATH}/IPD-1/edit`, PLANNING_ROUTES.ipdEdit, { ipdId: "IPD-1" }]]) {
		const route = router.resolve(path)
		assert.equal(route.name, name, path)
		assert.deepEqual(props(route), { ...extra, ipdRoutes: planning }, path)
	}
	assert.equal(router.resolve(ipdRoute("IPD-1", {}, planning)).path, `${PATH}/IPD-1`)
	assert.equal(router.resolve(ipdEditRoute("IPD-1", {}, planning)).path, `${PATH}/IPD-1/edit`)
	assert.equal(router.resolve(ipdEditRoute("IPD-1")).path, "/merch/item-production-details/IPD-1/edit")
	assert.equal(MERCH_IPD_ROUTES.view, MERCH_ROUTES.ipd)
})

test("the Production Planner layout opens Item Production Detail and the list needs IPD read", () => {
	const layout = JSON.parse(source("./data/yrp_ui_layout.json")).find((row) => row.name === "Production Planner")
	const workspaces = JSON.parse(layout.config).experience_props.workspaces
	const locked = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "planning" }, config: { experience_props: { workspaces } } } })
	assert.ok(workspaces.includes("item_production_details"))
	assert.ok(isWorkspaceInLayout({ key: "item_production_details", to: PATH }, locked))
	assert.equal(getLockedRedirect(loadRouter().resolve(`${PATH}/IPD-1/edit`), locked), undefined)
	assert.equal(canOpenList(PATH, { user: { name: "planner@example.com", can_read: ["YRP Item Production Detail"] } }), true)
	assert.equal(canOpenList(PATH, { user: { name: "planner@example.com", can_read: ["SD YRP Lot"] } }), false)
})

test("IPD links inside Planning open the Planning IPD page", () => {
	assert.equal(DEPARTMENT_RECORD_ROUTES["/planning"]["YRP Item Production Detail"]("IPD-1"), "/web/planning/item-production-details/IPD-1")
	assert.equal(DEPARTMENT_RECORD_ROUTES["/quality/lots"]["YRP Item Production Detail"], undefined)
})
