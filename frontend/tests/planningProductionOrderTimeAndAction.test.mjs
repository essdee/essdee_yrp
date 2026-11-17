import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

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
	assert.match(page, /<Tab v-if="showTimeAndAction && workspace.record\?.name" value="time_and_action">Time and Action<\/Tab>/)
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

test("Update dates is offered only for an In Progress T&A", () => {
	const tab = source("departments/planning/time-and-action/LotTimeAndActionTab.vue")
	assert.match(tab, /v-if="data.status === 'In Progress'"/)
})
