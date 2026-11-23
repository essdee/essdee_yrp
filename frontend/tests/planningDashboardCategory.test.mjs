import test from "node:test"
import assert from "node:assert/strict"

import { dashboardCsv, dashboardOptions, dashboardTotals, emptyDashboardFilters, filterDashboardRows, groupDashboardRows, hasDashboardFilter, sortDashboardRows, statusCards } from "../src/departments/planning/dashboard/dashboardRows.js"
import { drillQuery, readTrackingQuery, trackingQuery } from "../src/departments/planning/dashboard/routeFilters.js"
import { hasTrackingScope, pruneTrackingFilters, trackingFilterOptions, trackingSummary } from "../src/departments/planning/dashboard/trackingRows.js"

const lot = (values) => ({ has_work_order: true, status: "In sewing", status_rank: 500, qty: 100, total: 100, cut: 0, stitch: 0, packed: 0, dispatch: 0, balance: 100, ...values })
const rows = [
	lot({ lot: "L-1", ppo: "PPO-1", item: "A", product_category: "Thermal" }),
	lot({ lot: "L-2", ppo: "PPO-1", item: "B", product_category: "Vest", status: "In cutting", status_rank: 300 }),
	lot({ lot: "L-3", ppo: "PPO-2", item: "C", product_category: null }),
	lot({ lot: "L-4", ppo: "PPO-2", item: "D", product_category: "Thermal", has_work_order: false, status: "No Work Order yet", status_rank: 0 }),
]
const ppos = { "PPO-1": { item: "A", boxes: 10, pieces: 100 }, "PPO-2": { item: "C", boxes: 5, pieces: 50 } }

test("Product Category is a Dashboard filter that narrows rows, options and status cards", () => {
	const filters = { ...emptyDashboardFilters(), product_category: ["Thermal"] }
	assert.ok(hasDashboardFilter(filters))
	assert.deepEqual(filterDashboardRows(rows, filters).map((row) => row.lot), ["L-1", "L-4"])
	assert.deepEqual(dashboardOptions(rows, emptyDashboardFilters(), "product_category", ppos), [{ value: "Thermal", hint: "2 lots" }, { value: "Vest", hint: "1 lot" }])
	assert.deepEqual(dashboardOptions(rows, filters, "lot", ppos).map((option) => option.value), ["L-1", "L-4"])
	const totals = dashboardTotals({ as_of: "2026-11-23", ppos, lots: rows }, filters)
	assert.deepEqual(statusCards(totals.rows).map((card) => [card.status, card.count]), [["In sewing", 1], ["No Work Order yet", 1]])
	assert.deepEqual(totals.ppoNames, ["PPO-1", "PPO-2"])
})

test("Dashboard groups, sorts and copies the Product Category", () => {
	const groups = groupDashboardRows(rows.slice(0, 2))
	assert.equal(groups[0].product_category, "2 categories")
	assert.equal(groupDashboardRows([rows[0]])[0].product_category, "Thermal")
	const sorted = sortDashboardRows(rows, { key: "product_category", direction: 1 }, ppos)
	assert.deepEqual(sorted.map((row) => row.lot), ["L-3", "L-1", "L-4", "L-2"])
	const lines = dashboardCsv([rows[0]], false, ppos).split("\n")
	assert.equal(lines[0].split(",")[4], "Product Category")
	assert.equal(lines[1].split(",")[4], "Thermal")
})

test("Product Category lives in the URL across tabs and drills", () => {
	const query = trackingQuery({ filters: { ppo: [], lot: [], process: [], category: ["Thermal"] }, showDispatched: false })
	assert.deepEqual(query, { view: "tracking", category: ["Thermal"] })
	assert.deepEqual(readTrackingQuery({ view: "dashboard", category: "Thermal,Vest" }).filters.category, ["Thermal", "Vest"])
	assert.deepEqual(drillQuery({ ppo: ["PPO-1"], lot: [], dispatched: false, category: ["Thermal"] }), { view: "tracking", ppo: ["PPO-1"], category: ["Thermal"] })
})

test("PPO Tracking: a category alone is a scope and narrows PPO, Lot and not-started lots", () => {
	assert.ok(hasTrackingScope({ ppo: [], lot: [], process: [], category: ["Thermal"] }))
	assert.ok(!hasTrackingScope({ ppo: [], lot: [], process: [] }))
	const options = {
		ppos: [{ name: "PPO-1", item: "A", item_name: "A", product_categories: ["Thermal", "Vest"] }, { name: "PPO-2", item: "C", item_name: "C", product_categories: ["Thermal"] }, { name: "PPO-3", item: "E", item_name: "E", product_categories: [] }],
		lots: [{ name: "L-1", item: "A", ppo: "PPO-1", product_category: "Thermal" }, { name: "L-2", item: "B", ppo: "PPO-1", product_category: "Vest" }],
	}
	const filters = { ppo: [], lot: ["L-2"], process: [], category: ["Thermal"] }
	const result = trackingFilterOptions(options, [], filters)
	assert.deepEqual(result.ppo.map((option) => option.value), ["PPO-1", "PPO-2"])
	assert.deepEqual(result.lot.map((option) => option.value), ["L-1"])
	assert.deepEqual(result.category, [{ value: "Thermal", hint: "2 PPOs" }, { value: "Vest", hint: "1 PPO" }])
	assert.deepEqual(pruneTrackingFilters(filters, result), { ppo: [], lot: [], process: [], category: ["Thermal"] })
	const data = { ppos: { "PPO-1": { boxes: 1, pieces: 10, lots: [{ lot: "L-8", has_work_order: false, planned: 40, product_category: "Thermal" }, { lot: "L-9", has_work_order: false, planned: 60, product_category: "Vest" }] } }, lots: [] }
	const summary = trackingSummary(data, { ppo: ["PPO-1"], lot: [], process: [], category: ["Thermal"] })
	assert.deepEqual([summary.notStartedLots, summary.notStarted], [1, 40])
	const byCategory = trackingSummary({ ...data, lots: [{ lot: "L-1", ppo: "PPO-1", status: "In sewing", total: 10, dispatch: 0, product_category: "Thermal" }] }, { ppo: [], lot: [], process: [], category: ["Thermal"] })
	assert.deepEqual([byCategory.isLotsOnly, byCategory.notStartedLots], [false, 1])
})
