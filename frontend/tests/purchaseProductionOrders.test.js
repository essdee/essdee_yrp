import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"

import { ACCOUNTS_ROUTES } from "../src/departments/accounts/accountsViews.js"
import { MERCH_PD_ROUTES } from "../src/departments/merch-pd/merchPdRoutes.js"
import { merchPurchaseLauncherItems } from "../src/departments/merch-purchase/merchPurchaseViews.js"
import { MERCH_PURCHASE_ROUTES } from "../src/departments/merch-purchase/merchPurchaseRoutes.js"
import { MERCH_ROUTES, merchLauncherItems } from "../src/departments/merch/merchViews.js"
import { PD_ROUTES } from "../src/departments/pd/pdViews.js"
import { PLANNING_ROUTES } from "../src/departments/planning/planningViews.js"
import { PURCHASE_ROUTES, purchaseLauncherItems } from "../src/departments/purchase/purchaseViews.js"
import { QUALITY_ROUTES } from "../src/departments/quality/qualityRoutes.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"
import { getLockedDepartment, getLockedRedirect, isWorkspaceInLayout, LAYOUT_UNAVAILABLE_PATH } from "../src/router/departmentLock.js"
import { webDocumentPath } from "../src/router/webDocumentRoutes.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const plain = (value) => JSON.parse(JSON.stringify(value))

function loadRouter() {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, MERCH_PD_ROUTES, MERCH_PURCHASE_ROUTES, QUALITY_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH: "/no-permission" }
	vm.runInNewContext(routerSource, context)
	return context.router
}

test("the Purchase launcher shows the Production Order card after Lot", () => {
	const items = purchaseLauncherItems()
	assert.deepEqual(items.slice(0, 2).map((item) => item.key), ["lots", "production_orders"])
	const card = items.find((item) => item.key === "production_orders")
	const merchCard = merchLauncherItems().find((item) => item.key === "production_orders")
	assert.deepEqual([card.label, card.icon, card.to], [merchCard.label, merchCard.icon, "/purchase/production-orders"])
	assert.deepEqual(getWorkspacePaths(departments.find((item) => item.key === "purchase")).production_orders, ["/purchase/production-orders"])
})

test("Purchase reuses the Production Order list, page and editor inside Purchase", () => {
	const router = loadRouter()
	const page = (path) => router.resolve(path).matched.at(-1)
	const list = router.resolve("/purchase/production-orders")
	assert.equal(list.name, PURCHASE_ROUTES.productionOrders)
	assert.equal(page("/purchase/production-orders").components.default, page("/merch/production-orders").components.default)
	assert.deepEqual(plain(list.matched.at(-1).props.default), { backTo: "/purchase", backLabel: "Purchase", viewRouteName: PURCHASE_ROUTES.productionOrder, newRouteName: PURCHASE_ROUTES.productionOrderNew, eyebrow: "Purchase" })
	const view = router.resolve("/purchase/production-orders/PPO-1")
	assert.equal(view.name, PURCHASE_ROUTES.productionOrder)
	assert.equal(view.matched.at(-1).components.default, page("/merch/production-orders/PPO-1").components.default)
	assert.deepEqual(plain(view.matched.at(-1).props.default), { backTo: "/purchase/production-orders", backLabel: "Production Orders", viewRouteName: PURCHASE_ROUTES.productionOrder, transferViewRouteName: PURCHASE_ROUTES.productionOrder, editRouteName: PURCHASE_ROUTES.productionOrderEdit, listRouteName: PURCHASE_ROUTES.productionOrders })
	assert.equal(router.resolve("/purchase/production-orders/new").name, PURCHASE_ROUTES.productionOrderNew)
	const edit = router.resolve("/purchase/production-orders/PPO-1/edit")
	assert.equal(edit.name, PURCHASE_ROUTES.productionOrderEdit)
	assert.equal(edit.matched.at(-1).props.default(edit).productionOrderId, "PPO-1")
})

test("the Purchase layout opens Production Orders and keeps PO and PPO links inside Purchase", () => {
	const router = loadRouter()
	const layouts = JSON.parse(source("./data/yrp_ui_layout.json"))
	const workspaces = JSON.parse(layouts.find((layout) => layout.experience_key === "purchase").config).experience_props.workspaces
	assert.ok(workspaces.includes("production_orders"))
	const locked = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "purchase" }, config: { experience_props: { workspaces } } } })
	assert.ok(isWorkspaceInLayout({ to: "/purchase/production-orders" }, locked))
	for (const path of ["/purchase/production-orders", "/purchase/production-orders/new"]) assert.equal(getLockedRedirect(router.resolve(path), locked), undefined, path)
	assert.equal(webDocumentPath("YRP Production Order", "PPO/1", "/web/purchase/purchase-orders/PO-1"), "/web/purchase/production-orders/PPO%2F1")
	assert.equal(webDocumentPath("Purchase Order", "PO/1", "/web/purchase/production-orders/PPO-1"), "/web/purchase/purchase-orders/PO%2F1")
	assert.equal(webDocumentPath("YRP Production Order", "PPO/1", "/web/fabric-store/purchase-orders/PO-1"), "/web/sales/production-orders/PPO%2F1")
})

test("Merch & Purchase keeps one Production Order card, the Merch one", () => {
	const cards = merchPurchaseLauncherItems().filter((item) => item.key === "production_orders")
	assert.deepEqual(cards.map((item) => item.to), ["/merch/production-orders"])
})
