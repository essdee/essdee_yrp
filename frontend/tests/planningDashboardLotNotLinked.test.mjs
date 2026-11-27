import test from "node:test"
import assert from "node:assert/strict"

import { LOT_NOT_LINKED, LOTS_CLOSED, isPpoOnlyRow, dashboardCsv, dashboardOptions, dashboardTotals, emptyDashboardFilters, filterDashboardRows, groupDashboardRows, orderStatuses, sortDashboardRows, statusCards, statusTone } from "../src/departments/planning/dashboard/dashboardRows.js"

const lot = (values) => ({ has_work_order: true, status: "In sewing", status_rank: 600, qty: 100, ppo_qty: 100, cut: 0, stitch: 0, packed: 0, dispatch: 0, balance: 100, ...values })
const unlinked = { lot: null, ppo: "PPO-9", item: "VEST-7", item_name: "Casual Designer Vest - 7", delivery: "2026-10-15", boxes: 4000, ppo_qty: null, has_work_order: false, status: LOT_NOT_LINKED, status_rank: 100 }
const rows = [
	lot({ lot: "L-1", ppo: "PPO-1", item: "A" }),
	lot({ lot: "L-2", ppo: "PPO-1", item: "A", status: "PO Created", status_rank: 300, has_work_order: false }),
	unlinked,
]
const ppos = { "PPO-1": { item: "A", boxes: 10, pieces: 100 }, "PPO-9": { item: "VEST-7", item_name: "Casual Designer Vest - 7", boxes: 4000, pieces: null } }
const data = { as_of: "2026-11-27", ppos, lots: rows }

test("Lot not linked is its own status, ordered before PO Created", () => {
	assert.equal(LOT_NOT_LINKED, "Lot not linked")
	assert.deepEqual(orderStatuses(rows), [LOT_NOT_LINKED, "PO Created", "In sewing"])
	assert.deepEqual(dashboardOptions(rows, emptyDashboardFilters(), "status", ppos).map((option) => option.value), [LOT_NOT_LINKED, "PO Created", "In sewing"])
	assert.equal(statusTone(LOT_NOT_LINKED), "red")
	assert.deepEqual(sortDashboardRows(rows, { key: "status", direction: 1 }).map((row) => row.ppo), ["PPO-9", "PPO-1", "PPO-1"])
})

test("A lot-less PPO is in the PPO filter and filters to its row; never a Lot option", () => {
	const options = dashboardOptions(rows, emptyDashboardFilters(), "ppo", ppos)
	assert.deepEqual(options.find((option) => option.value === "PPO-9"), { value: "PPO-9", hint: "Casual Designer Vest - 7 · Lot not linked" })
	assert.deepEqual(dashboardOptions(rows, emptyDashboardFilters(), "lot", ppos).map((option) => option.value), ["L-1", "L-2"])
	const filters = { ...emptyDashboardFilters(), ppo: ["PPO-9"] }
	assert.deepEqual(filterDashboardRows(rows, filters), [unlinked])
	assert.deepEqual(filterDashboardRows(rows, { ...emptyDashboardFilters(), status: [LOT_NOT_LINKED] }), [unlinked])
})

test("Lot-based totals ignore lot-less rows; the table and status cards show them", () => {
	const totals = dashboardTotals(data, emptyDashboardFilters())
	assert.deepEqual(totals.tableRows.map((row) => row.ppo), ["PPO-1", "PPO-1", "PPO-9"])
	assert.deepEqual(totals.rows.map((row) => row.lot), ["L-1", "L-2"])
	assert.deepEqual(totals.ppoNames, ["PPO-1"])
	assert.equal(totals.notStarted.length, 1)
	assert.equal(totals.ppoQty, 200)
	assert.deepEqual(statusCards(totals.tableRows).map((card) => [card.status, card.count]), [[LOT_NOT_LINKED, 1], ["PO Created", 1], ["In sewing", 1]])
})

test("Grouping and CSV keep a lot-less PPO without a lot", () => {
	const group = groupDashboardRows([unlinked])[0]
	assert.equal(group.lot, "")
	assert.equal(group.lotCount, 0)
	assert.equal(group.status, LOT_NOT_LINKED)
	const line = dashboardCsv([unlinked], false, ppos).split("\n")[1].split(",")
	assert.deepEqual(line.slice(1, 7), ["PPO-9", "", "VEST-7", "", LOT_NOT_LINKED, ""])
})

test("Process Status keeps only lot rows", async () => {
	const { processStatusRows } = await import("../src/departments/planning/dashboard/processStatusRows.js")
	assert.deepEqual(processStatusRows(data, { lots: {} }).map((row) => row.lot), ["L-1", "L-2"])
})

const closed = { lot: null, closed_lots: "F-1/1 (Closed)", ppo: "PPO-8", item: "TEE", delivery: "2026-10-20", ppo_qty: 50, has_work_order: false, status: LOTS_CLOSED, status_rank: 200 }
const withClosed = [...rows, closed]

test("Lots closed, PPO open sits right after Lot not linked and counts PPOs", () => {
	assert.equal(LOTS_CLOSED, "Lots closed, PPO open")
	assert.deepEqual(orderStatuses(withClosed), [LOT_NOT_LINKED, LOTS_CLOSED, "PO Created", "In sewing"])
	assert.equal(dashboardOptions(withClosed, emptyDashboardFilters(), "status", ppos).find((option) => option.value === LOTS_CLOSED).hint, "1 PPO")
	assert.deepEqual(dashboardOptions(withClosed, emptyDashboardFilters(), "ppo", ppos).find((option) => option.value === "PPO-8").hint, " · Lots closed, PPO open")
	assert.deepEqual(filterDashboardRows(withClosed, { ...emptyDashboardFilters(), status: [LOTS_CLOSED] }), [closed])
	assert.ok(isPpoOnlyRow(closed) && isPpoOnlyRow(unlinked))
	const cards = statusCards(withClosed)
	assert.deepEqual(cards.map((card) => [card.status, card.count, card.ppoCaption]), [[LOT_NOT_LINKED, 1, "open PPOs with no lot"], [LOTS_CLOSED, 1, "open PPOs whose lots are all closed"], ["PO Created", 1, undefined], ["In sewing", 1, undefined]])
})

test("Lots closed rows stay out of lot totals; CSV and grouping show the closed lots", () => {
	const totals = dashboardTotals({ ...data, lots: withClosed }, emptyDashboardFilters())
	assert.deepEqual(totals.rows.map((row) => row.lot), ["L-1", "L-2"])
	assert.equal(totals.ppoQty, 200)
	const group = groupDashboardRows([closed])[0]
	assert.equal(group.status, LOTS_CLOSED)
	assert.equal(group.lotCount, 0)
	assert.equal(group.closed_lots, "F-1/1 (Closed)")
	const line = dashboardCsv([closed], false, ppos).split("\n")[1]
	assert.ok(line.includes("PPO-8,F-1/1 (Closed),TEE"))
	assert.deepEqual(sortDashboardRows(withClosed, { key: "status", direction: 1 }).map((row) => row.ppo), ["PPO-9", "PPO-8", "PPO-1", "PPO-1"])
})
