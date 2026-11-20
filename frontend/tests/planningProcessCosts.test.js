import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"

import { ACCOUNTS_ROUTES } from "../src/departments/accounts/accountsViews.js"
import { MERCH_ROUTES } from "../src/departments/merch/merchViews.js"
import { MERCH_PROCESS_COST_ROUTES, processCostPath } from "../src/departments/merch/process-cost/processCostViews.js"
import { PD_ROUTES } from "../src/departments/pd/pdViews.js"
import { PLANNING_ROUTES, PLANNING_WORKSPACES, visiblePlanningWorkspaces } from "../src/departments/planning/planningViews.js"
import { PURCHASE_ROUTES } from "../src/departments/purchase/purchaseViews.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"
import { MERCH_PD_ROUTES } from "../src/departments/merch-pd/merchPdRoutes.js"
import { MERCH_PURCHASE_ROUTES } from "../src/departments/merch-purchase/merchPurchaseRoutes.js"
import { QUALITY_ROUTES } from "../src/departments/quality/qualityRoutes.js"
import { getLockedRedirect, isWorkspaceInLayout, LAYOUT_UNAVAILABLE_PATH } from "../src/router/departmentLock.js"
import { lockedDepartment } from "./helpers/layout.js"
import { canOpenList, NO_PERMISSION_PATH } from "../src/router/listPermission.js"
import { DEPARTMENT_RECORD_ROUTES } from "../src/router/webDocumentRoutes.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const PATH = "/planning/process-costs"
const PLANNING = { department: "Planning", departmentPath: "/planning", listPath: PATH, list: PLANNING_ROUTES.processCosts, new: PLANNING_ROUTES.processCostNew, view: PLANNING_ROUTES.processCost, edit: PLANNING_ROUTES.processCostEdit, workOrder: PLANNING_ROUTES.workOrder }

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

test("Planning shows the shared Process Cost card under its own path", () => {
	const card = PLANNING_WORKSPACES.find((item) => item.key === "process_costs")
	assert.deepEqual([card.label, card.to], ["Process Cost", PATH])
	assert.deepEqual(visiblePlanningWorkspaces({ process_costs: { can_read: true } }).map((item) => item.key), ["process_costs"])
	assert.deepEqual(visiblePlanningWorkspaces({ process_costs: { can_read: false } }), [])
	assert.deepEqual(getWorkspacePaths(departments.find((item) => item.key === "planning")).process_costs, [PATH])
})

test("Planning Process Cost list, new, view and edit routes reuse the Merch pages with Planning route names", () => {
	const router = loadRouter()
	for (const [path, name, extra] of [[PATH, PLANNING_ROUTES.processCosts, {}], [`${PATH}/new`, PLANNING_ROUTES.processCostNew, {}], [`${PATH}/PC-1`, PLANNING_ROUTES.processCost, { processCostId: "PC-1" }], [`${PATH}/PC-1/edit`, PLANNING_ROUTES.processCostEdit, { processCostId: "PC-1" }]]) {
		const route = router.resolve(path)
		assert.equal(route.name, name, path)
		assert.deepEqual(props(route), { ...extra, processCostRoutes: PLANNING }, path)
	}
	assert.equal(processCostPath("PC-1", PLANNING), `${PATH}/PC-1`)
	assert.equal(processCostPath("PC-1"), "/merch/process-costs/PC-1")
	assert.equal(router.resolve({ name: PLANNING.edit, params: { processCostId: "PC-1" } }).path, `${PATH}/PC-1/edit`)
	assert.equal(router.resolve({ name: MERCH_PROCESS_COST_ROUTES.edit, params: { processCostId: "PC-1" } }).path, "/merch/process-costs/PC-1/edit")
	assert.equal(MERCH_PROCESS_COST_ROUTES.workOrder, MERCH_ROUTES.workOrder)
	assert.equal(props(router.resolve("/planning/work-orders/WO-1")).processCostViewRouteName, PLANNING_ROUTES.processCost)
})

test("a Planning layout opens Process Cost and the list needs Process Cost read", () => {
	const locked = lockedDepartment("planning", ["process_costs"])
	assert.ok(isWorkspaceInLayout({ key: "process_costs", to: PATH }, locked))
	assert.equal(getLockedRedirect(loadRouter().resolve(`${PATH}/PC-1/edit`), locked), undefined)
	assert.equal(canOpenList(PATH, { user: { name: "planner@example.com", can_read: ["YRP Process Cost"] } }), true)
	assert.equal(canOpenList(PATH, { user: { name: "planner@example.com", can_read: ["SD YRP Lot"] } }), false)
})

test("Process Cost links inside Planning open the Planning Process Cost page", () => {
	assert.equal(DEPARTMENT_RECORD_ROUTES["/planning"]["YRP Process Cost"]("PC-1"), "/web/planning/process-costs/PC-1")
	assert.equal(DEPARTMENT_RECORD_ROUTES["/merch"]["YRP Process Cost"]("PC-1"), "/web/merch/process-costs/PC-1")
})
