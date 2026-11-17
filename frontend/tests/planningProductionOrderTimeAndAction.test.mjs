import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { departments } from "../src/departments/registry.js"
import { isOutsideLayout } from "../src/router/departmentLock.js"
import { lotTimeAndActionUpdateRouteName } from "../src/departments/planning/time-and-action/timeAndActionRoutes.js"
import {
	convertConfirmMessage, createTimeAndActionActions, isFrozen, lotOptionLabel, toggleLot,
} from "../src/departments/planning/time-and-action/productionOrderTimeAndAction.js"

const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

test("a Frozen Production Order T&A is recognised", () => {
	assert.equal(isFrozen({ status: "Frozen" }), true)
	assert.equal(isFrozen({ status: "In Progress" }), false)
	assert.equal(isFrozen(null), false)
})

test("convertible lot option shows Lot, Item and Qty", () => {
	assert.equal(lotOptionLabel({ name: "LOT-1", item: "TEE", qty: 1200 }), "LOT-1 · TEE · Qty 1200")
	assert.equal(lotOptionLabel({ name: "LOT-2", item: null, qty: null }), "LOT-2 · Qty 0")
})

test("toggling lots keeps the eligible-lot order", () => {
	const eligible = [{ name: "LOT-1" }, { name: "LOT-2" }, { name: "LOT-3" }]
	assert.deepEqual(toggleLot([], "LOT-3", eligible), ["LOT-3"])
	assert.deepEqual(toggleLot(["LOT-3"], "LOT-1", eligible), ["LOT-1", "LOT-3"])
	assert.deepEqual(toggleLot(["LOT-1", "LOT-3"], "LOT-1", eligible), ["LOT-3"])
})

test("convert confirmation names the lots and the freeze", () => {
	assert.equal(
		convertConfirmMessage("TA-2026-00001", ["LOT-1", "LOT-2"]),
		"Create 2 Lot T&As (LOT-1, LOT-2) as copies of TA-2026-00001: rows, dependencies, work stations, dates, actual dates and reasons. TA-2026-00001 is then frozen and each Lot continues on its own.",
	)
	assert.match(convertConfirmMessage("TA-1", ["LOT-1"]), /^Create 1 Lot T&A \(LOT-1\)/)
})

test("Planning Production Order page has a Time and Action tab; Sales does not", () => {
	const router = source("router/index.js")
	const planningRoute = router.split("\n").find((line) => line.includes("listRouteName: PLANNING_ROUTES.productionOrders"))
	assert.match(planningRoute, /showTimeAndAction: true/)
	const page = source("departments/sales/ProductionOrder.vue")
	assert.match(page, /showTimeAndAction: \{ type: Boolean, default: false \}/)
	assert.match(page, /<Tab v-if="showTimeAndAction && workspace.record\?.name && timeAndAction.context.value\?.can_read" value="time_and_action">Time and Action<\/Tab>/)
})

test("Create T&A dialog creates against the given DocType", () => {
	const dialog = source("departments/planning/time-and-action/CreateTimeAndActionDialog.vue")
	assert.match(dialog, /createTimeAndAction\(props.against, props.againstId,/)
	const tab = source("departments/planning/time-and-action/ProductionOrderTimeAndActionTab.vue")
	assert.match(tab, /label="Convert to Lot T&A"/)
	const page = source("departments/sales/ProductionOrder.vue")
	assert.match(page, /<CreateTimeAndActionDialog v-if="showTimeAndAction && workspace.record\?.name"[^>]*against="YRP Production Order"/)
})

test("Create T&A is a header action only while the order can get a T&A", () => {
	let opened = 0
	const [action] = createTimeAndActionActions({ can_create: true }, { busy: false, onCreate: () => { opened += 1 } })
	assert.equal(action.label, "Create T&A")
	assert.equal(action.disabled, false)
	action.command()
	assert.equal(opened, 1)
	assert.equal(createTimeAndActionActions({ can_create: true }, { busy: true, onCreate() {} })[0].disabled, true)
	assert.deepEqual(createTimeAndActionActions({ can_create: false }, { busy: false, onCreate() {} }), [])
	assert.deepEqual(createTimeAndActionActions(null, { busy: false, onCreate() {} }), [])
})

test("Production Order page loads the T&A context and offers Create T&A in its actions", () => {
	const page = source("departments/sales/ProductionOrder.vue")
	assert.match(page, /useProductionOrderTimeAndAction\(/)
	assert.match(page, /const actions = computed\(\(\) => \[\.\.\.createTimeAndActionActions\(timeAndAction\.context\.value/, "Create T&A leads the secondary actions so it stays visible")
	assert.match(page, /<ProductionOrderTimeAndActionTab [^>]*:context="timeAndAction\.context\.value"[^>]*@create="createTimeAndActionVisible = true"/)
})

test("Update dates is offered only for an In Progress T&A the user can update; Lot Detail only with tracking access", () => {
	const tab = source("departments/planning/time-and-action/LotTimeAndActionTab.vue")
	assert.match(tab, /v-if="data.status === 'In Progress' && data.can_update_dates"/)
	assert.match(source("departments/planning/time-and-action/TimeAndActionHeader.vue"), /<Button v-if="data.can_view_lot_detail" label="Lot Detail"/)
})

test("Merch Production Order page shows the T&A tab and updates dates on the Merch route", () => {
	const router = source("router/index.js")
	const merchRoute = router.split("\n").find((line) => line.includes("listRouteName: MERCH_ROUTES.productionOrders"))
	assert.match(merchRoute, /showTimeAndAction: true, timeAndActionUpdateRouteName: "merch-lot-time-and-action-update"/)
	assert.match(source("departments/sales/ProductionOrder.vue"), /:update-route-name="timeAndActionUpdateRouteName"/)
	assert.match(source("departments/planning/time-and-action/ProductionOrderTimeAndActionTab.vue"), /:update-route-name="updateRouteName"/)
	assert.match(source("departments/planning/time-and-action/LotTimeAndActionTab.vue"), /:to="\{ name: updateRouteName, query:/)
	assert.match(source("departments/planning/time-and-action/TimeAndActionUpdate.vue"), /:back-to="backTo" :back-label="backLabel"/)
})

test("a Production Order with linked Lots shows the Create-from-Lot hint instead of Create T&A", () => {
	assert.match(source("departments/planning/time-and-action/LotTimeAndActionTab.vue"), /v-else-if="createBlockedReason === 'linked_lots'"[^>]*>Lots are linked to this Production Order\. Create the T&A from the Lot\.<\/Message>/)
	assert.match(source("departments/planning/time-and-action/ProductionOrderTimeAndActionTab.vue"), /:create-blocked-reason="context\?\.create_blocked_reason \|\| ''"/)
	assert.deepEqual(createTimeAndActionActions({ can_create: false, create_blocked_reason: "linked_lots" }, { busy: false, onCreate() {} }), [])
})

test("each Lot department's T&A update page is reachable from its locked layout", () => {
	for (const key of ["purchase", "merch", "merch-pd", "merch-purchase", "accounts", "quality"]) {
		const layout = { ...departments.find((item) => item.key === key), workspaces: ["lots"] }
		assert.equal(isOutsideLayout(`/${key}/lots/time-and-action-update`, layout), false, key)
		assert.equal(isOutsideLayout("/planning/time-and-action-update", layout), true, key)
	}
	assert.equal(lotTimeAndActionUpdateRouteName("planning"), "planning-time-and-action-update")
	assert.equal(lotTimeAndActionUpdateRouteName("merch-pd"), "merch-pd-lot-time-and-action-update")
})

test("Lot links follow the current department", async () => {
	const { departmentLotLocation } = await import("../src/departments/planning/time-and-action/timeAndAction.js")
	assert.deepEqual(departmentLotLocation("/merch/production-orders/PPO-1", "F 1/2", "time-and-action"), { path: "/merch/lots/F%201%2F2", query: { tab: "time-and-action" } })
	assert.deepEqual(departmentLotLocation("/planning/production-orders/PPO-1", "L1"), { path: "/planning/lots/L1", query: {} })
	assert.deepEqual(departmentLotLocation("/sales/production-orders/PPO-1", "L1"), { path: "/planning/lots/L1", query: {} })
	assert.match(source("departments/planning/time-and-action/ProductionOrderTimeAndActionTab.vue"), /<RouterLink :to="departmentLotLocation\(route\.path, copy\.lot, 'time-and-action'\)">\{\{ copy\.name \}\} \(\{\{ copy\.lot \}\}\)<\/RouterLink>/)
	assert.match(source("departments/planning/time-and-action/LotDetailDialog.vue"), /:to="departmentLotLocation\(route\.path, row\.lot\)"/)
})

const LOT_PAGES = {
	planning: "planning/lot/LotPage.vue",
	purchase: "purchase/lot/LotPage.vue",
	quality: "quality/lot/LotPage.vue",
	merch: "merch/lot/MerchLotPage.vue",
	"merch-pd": "merch-pd/lot/MerchLotPage.vue",
	"merch-purchase": "merch-purchase/lot/MerchLotPage.vue",
	accounts: "accounts/lot/MerchLotPage.vue",
}

test("every department Lot page has the Time and Action tab, gated on T&A read", () => {
	for (const [key, path] of Object.entries(LOT_PAGES)) {
		const page = source(`departments/${path}`)
		assert.match(page, /<Tab v-for="tab in timeAndAction\.withTab\(LOT_(VIEW_)?TABS\)"/, key)
		assert.match(page, /<TabPanel v-else-if="activeTab === 'time-and-action' && timeAndAction\.canRead" value="time-and-action">\s*<LotTimeAndActionTab v-bind="timeAndAction\.tabProps" @create="timeAndAction\.createVisible = true" @reverted="timeAndAction\.changed"/, key)
		assert.match(page, new RegExp(`useLotTimeAndActionTab\\(\\{ lotId: \\(\\) => props\\.lotId, department: "${key}", activeTab, onChanged: `), key)
		assert.match(page, /\.\.\.timeAndAction\.actions\(acting\.value\)/, key)
		assert.match(page, /<CreateTimeAndActionDialog v-model:visible="timeAndAction\.createVisible" v-bind="timeAndAction\.dialogProps" @created="timeAndAction\.created" \/>/, key)
	}
})

test("the Lot T&A composable shows the tab and Create only with T&A read", () => {
	const composable = source("departments/planning/time-and-action/useLotTimeAndActionTab.js")
	assert.match(composable, /const canRead = computed\(\(\) => Boolean\(context\.value\?\.can_read\)\)/)
	assert.match(composable, /\.\.\.\(canRead\.value \? \[TIME_AND_ACTION_TAB\] : \[\]\)/)
	assert.match(composable, /if \(context\.value && !canRead\.value && activeTab\.value === TIME_AND_ACTION_TAB\.key\) activeTab\.value = "lot"/)
	assert.deepEqual(createTimeAndActionActions({ can_read: false }, { busy: false, onCreate() {} }), [])
})
