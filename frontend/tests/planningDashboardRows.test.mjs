import test from "node:test"
import assert from "node:assert/strict"

import {
	NO_WORK_ORDER,
	PO_CREATED,
	dashboardCsv,
	dashboardOptions,
	dashboardTotals,
	filterDashboardRows,
	groupDashboardRows,
	rowDrill,
	sortDashboardRows,
	statusCards,
	statusTone,
	tileDrill,
} from "../src/departments/planning/dashboard/dashboardRows.js"
import { windowRows } from "../src/departments/planning/dashboard/rowWindow.js"
import { dashboardTiles } from "../src/departments/planning/dashboard/summaryCards.js"

const ppos = {
	"PPO-1": { item: "A", item_name: "Alpha", boxes: 100, pieces_per_box: 10, pieces: 1000, delivery: "2026-10-01" },
	"PPO-2": { item: "B", item_name: "Beta", boxes: 50.5, pieces_per_box: null, pieces: null, delivery: "2026-12-01" },
	"PPO-3": { item: "C", item_name: "Gamma", boxes: 10, pieces_per_box: 5, pieces: 50, delivery: "2026-12-01" },
}
const lot = (values) => ({ has_work_order: true, cut: 0, stitch: 0, packed: 0, dispatch: 0, total: 0, balance: 0, qty: 0, ...values })
const rows = [
	lot({ lot: "L-2", ppo: "PPO-1", item: "A", status: "In sewing", status_rank: 500, delivery: "2026-10-01", qty: 400, cut: 410, stitch: 100, total: 410, balance: 410 }),
	lot({ lot: "L-1", ppo: "PPO-1", item: "A", status: "Dispatched", status_rank: 800, delivery: "2026-10-01", qty: 500, cut: 520, stitch: 520, packed: 500, dispatch: 500, total: 520, balance: 20 }),
	lot({ lot: "L-10", ppo: "PPO-2", item: "B", status: "Fabric not received", status_rank: 100, delivery: "2026-12-01", qty: 300, total: 300, balance: 0 }),
	{ lot: "L-3", ppo: "PPO-1", item: "A", status: NO_WORK_ORDER, status_rank: 0, has_work_order: false, delivery: "2026-10-01", qty: 250, cut: 0, stitch: 0, packed: 0, dispatch: 0, total: 0, balance: 0 },
]
const data = { as_of: "2026-11-06", ppos, lots: rows }
const empty = { ppo: [], lot: [], item: [], status: [] }

test("filters narrow rows and options ignore their own filter", () => {
	const filters = { ...empty, status: ["In sewing"] }
	assert.deepEqual(filterDashboardRows(rows, filters).map((row) => row.lot), ["L-2"])
	assert.deepEqual(dashboardOptions(rows, filters, "status", ppos).map((option) => option.value), ["Fabric not received", "In sewing", "Dispatched", NO_WORK_ORDER])
	assert.deepEqual(dashboardOptions(rows, filters, "ppo", ppos), [{ value: "PPO-1", hint: "Alpha · 1 lot" }])
	assert.deepEqual(dashboardOptions(rows, { ...empty, item: ["B"] }, "lot", ppos), [{ value: "L-10", hint: "B" }])
})

test("tiles add up exactly the table rows, with or without a filter", () => {
	const all = dashboardTotals(data, empty)
	assert.equal(all.ppoCount, 2)
	assert.equal(all.allPpoCount, 3)
	assert.equal(all.ppoPieces, 1000)
	assert.deepEqual(all.withoutPieces, [{ name: "PPO-2", boxes: 50.5 }])
	assert.equal(all.lotQty, 1450)
	assert.equal(all.lots.length, 3)
	assert.equal(all.open.length, 2)
	assert.equal(all.cut, 930)
	assert.equal(all.dispatched, 500)
	assert.equal(all.balance, 430)
	assert.deepEqual(all.late.map((row) => row.lot), ["L-2"])
	assert.equal(all.notStarted.length, 1)
	assert.equal(all.ppoWithWorkOrders, 2)
	const filtered = dashboardTotals(data, { ...empty, item: ["B"] })
	assert.equal(filtered.ppoCount, 1)
	assert.equal(filtered.ppoPieces, 0)
	assert.equal(filtered.withoutPieces.length, 1)
})

test("every card equals the sum of its table column for each filter", () => {
	const cutting = lot({ lot: "L-20", ppo: "PPO-3", item: "C", status: "In cutting", status_rank: 400, qty: 900, total: 900, cut: 0, balance: 0 })
	const moved = lot({ lot: "L-21", ppo: "PPO-3", item: "C", status: "In cutting", status_rank: 400, qty: 100, cut: 100, dispatch: 10, to_alternative: 30, balance: 60 })
	const all = { ...data, lots: [...rows, cutting, moved] }
	const column = (list, field) => list.reduce((total, row) => total + (row[field] || 0), 0)
	for (const filters of [empty, { ...empty, status: ["In cutting"] }, { ...empty, item: ["A"] }, { ...empty, lot: ["L-2", "L-21"] }]) {
		const totals = dashboardTotals(all, filters)
		assert.equal(totals.cut, column(totals.rows, "cut"))
		assert.equal(totals.dispatched, column(totals.rows, "dispatch"))
		assert.equal(totals.balance, column(totals.rows, "balance"))
		assert.equal(totals.balance, totals.cut - totals.cutDispatched - totals.cutMoved)
		assert.ok(totals.balance <= totals.cut)
	}
	const inCutting = dashboardTotals(all, { ...empty, status: ["In cutting"] })
	assert.deepEqual([inCutting.ppoCount, inCutting.cut, inCutting.balance, inCutting.uncutLots, inCutting.moved], [1, 100, 60, 1, 30])
	const grouped = groupDashboardRows(inCutting.rows)
	assert.deepEqual([grouped[0].balance, grouped[0].to_alternative], [60, 30])
})

test("status cards add up to the rows and use Lot pcs for lots with no Work Order", () => {
	const cards = statusCards(dashboardTotals(data, empty).rows)
	assert.deepEqual(cards.map((card) => [card.status, card.count, card.pieces]), [
		["Fabric not received", 1, 300], ["In sewing", 1, 410], ["Dispatched", 1, 520], [NO_WORK_ORDER, 1, 250],
	])
})

test("fabric process statuses order by rank between Fabric not received and Waiting for cutting", () => {
	const processRows = [
		lot({ lot: "P-1", ppo: "PPO-3", item: "C", status: "Waiting for cutting", status_rank: 200, total: 50 }),
		lot({ lot: "P-2", ppo: "PPO-3", item: "C", status: "Washing", status_rank: 103, total: 40 }),
		lot({ lot: "P-3", ppo: "PPO-3", item: "C", status: "Knitting", status_rank: 101, total: 30 }),
		lot({ lot: "P-4", ppo: "PPO-3", item: "C", status: "Dyeing", status_rank: 102, total: 20 }),
		{ lot: "P-5", ppo: "PPO-3", item: "C", status: "Fabric not received", status_rank: 100, has_work_order: false, qty: 70, total: 0 },
	]
	assert.deepEqual(statusCards(processRows).map((card) => [card.status, card.pieces]), [
		["Fabric not received", 70], ["Knitting", 30], ["Dyeing", 20], ["Washing", 40], ["Waiting for cutting", 50],
	])
	assert.deepEqual(dashboardOptions(processRows, empty, "status", ppos).map((option) => option.value), ["Fabric not received", "Knitting", "Dyeing", "Washing", "Waiting for cutting"])
	const group = groupDashboardRows(processRows.slice(0, 4))[0]
	assert.equal(group.status, "Knitting")
	assert.equal(group.breakdown, "Knitting: 1\nDyeing: 1\nWashing: 1\nWaiting for cutting: 1")
	assert.deepEqual(sortDashboardRows(processRows, { key: "status", direction: 1 }, ppos).map((row) => row.lot), ["P-5", "P-3", "P-4", "P-2", "P-1"])
	assert.deepEqual(["Knitting", "In cutting", NO_WORK_ORDER].map(statusTone), ["process", "amber", "neutral"])
})

test("PO Created and Yarn / Fabric Received sit before fabric processes and a split lot counts in both cards", () => {
	const split = { status: PO_CREATED, status_rank: 100, pieces: 600 }
	const purchaseRows = [
		lot({ lot: "S-1", ppo: "PPO-3", item: "C", status: "Knitting", status_rank: 301, total: 1000, qty: 1000, purchase_split: split }),
		{ lot: "S-2", ppo: "PPO-3", item: "C", status: PO_CREATED, status_rank: 100, has_work_order: false, qty: 500, total: 0 },
		{ lot: "S-3", ppo: "PPO-3", item: "C", status: "Yarn / Fabric Received", status_rank: 200, has_work_order: false, qty: 300, total: 0 },
		{ lot: "S-4", ppo: "PPO-3", item: "C", status: NO_WORK_ORDER, status_rank: 0, has_work_order: false, qty: 50, total: 0 },
	]
	assert.deepEqual(statusCards(purchaseRows).map((card) => [card.status, card.count, card.pieces]), [
		[PO_CREATED, 2, 1100], ["Yarn / Fabric Received", 1, 300], ["Knitting", 1, 400], [NO_WORK_ORDER, 1, 50],
	])
	assert.deepEqual(filterDashboardRows(purchaseRows, { ...empty, status: [PO_CREATED] }).map((row) => row.lot), ["S-1", "S-2"])
	assert.deepEqual(dashboardOptions(purchaseRows, empty, "status", ppos).map((option) => [option.value, option.hint]), [
		[PO_CREATED, "2 lots"], ["Yarn / Fabric Received", "1 lot"], ["Knitting", "1 lot"], [NO_WORK_ORDER, "1 lot"],
	])
	assert.equal(groupDashboardRows(purchaseRows.slice(0, 3))[0].breakdown, "PO Created: 2\nYarn / Fabric Received: 1\nKnitting: 1")
	assert.deepEqual([PO_CREATED, "Yarn / Fabric Received"].map(statusTone), ["amber", "blue"])
})

test("group by PPO sums lots, keeps PPO qty once and shows the furthest-behind open status", () => {
	const groups = groupDashboardRows(rows)
	const first = groups.find((row) => row.ppo === "PPO-1")
	assert.equal(first.lotCount, 3)
	assert.equal(first.lot, "L-2, L-1, L-3")
	assert.equal(first.qty, 1150)
	assert.equal(first.cut, 930)
	assert.equal(first.dispatch, 500)
	assert.equal(first.status, NO_WORK_ORDER)
	assert.equal(first.otherStatuses, 2)
	assert.equal(groupDashboardRows([rows[1]])[0].status, "Dispatched")
	assert.equal(groupDashboardRows([rows[0], rows[1]])[0].status, "In sewing")
})

test("sorting is numeric-aware and reversible; rows render in scroll chunks", () => {
	const byLot = sortDashboardRows(rows, { key: "lot", direction: 1 }, ppos).map((row) => row.lot)
	assert.deepEqual(byLot, ["L-1", "L-2", "L-3", "L-10"])
	const byCut = sortDashboardRows(rows, { key: "cut", direction: -1 }, ppos).map((row) => row.lot)
	assert.equal(byCut[0], "L-1")
	const many = Array.from({ length: 120 }, (_, index) => ({ lot: String(index) }))
	assert.deepEqual([windowRows(many, 60).rows.length, windowRows(many, 60).hasMore, windowRows(many, 180).rows.length, windowRows(many, 180).hasMore], [60, true, 120, false])
})

test("CSV writes every row with the PPO qty unit", () => {
	const text = dashboardCsv(sortDashboardRows(rows, { key: "ppo", direction: 1 }, ppos), false, ppos)
	const lines = text.split("\n")
	assert.equal(lines[0], "#,PPO,Lot,Item,Product Category,Status,PPO Qty,PPO Qty unit,Lot Qty,Cut Qty,Stitching Qty,Packed Qty,Dispatched Qty,Moved to alternative,Balance")
	assert.equal(lines.length, 5)
	assert.ok(lines.some((line) => line.includes("PPO-2,L-10,B,,Fabric not received,50.5,box")))
	const grouped = dashboardCsv(groupDashboardRows(rows), true, ppos).split("\n")
	assert.equal(grouped[0].split(",")[2], "Lots")
	assert.ok(grouped[1].includes('"L-2, L-1, L-3"'))
})

test("drills open PPO Tracking with the tile or row selection", () => {
	const totals = dashboardTotals(data, empty)
	assert.deepEqual(tileDrill("ppos", totals), { ppo: ["PPO-1", "PPO-2"], lot: [], dispatched: false })
	assert.deepEqual(tileDrill("cut", totals), { ppo: [], lot: ["L-2", "L-1"], dispatched: true })
	assert.deepEqual(tileDrill("late", totals), { ppo: [], lot: ["L-2"], dispatched: false })
	assert.deepEqual(rowDrill(rows[1], true), { ppo: ["PPO-1"], lot: ["L-1"], dispatched: true })
	assert.deepEqual(rowDrill(rows[0], false), { ppo: ["PPO-1"], lot: [], dispatched: false })
})

test("tiles say their formula in a hover card and never mention boxes-only counts", () => {
	const tiles = dashboardTiles(dashboardTotals(data, empty))
	const byKey = Object.fromEntries(tiles.map((tile) => [tile.key, tile]))
	assert.ok(tiles.every((tile) => tile.help?.formula && !("title" in tile)))
	assert.equal(byKey.ppoQty.foot, "pcs · 1 PPO not counted (no pcs per box)")
	assert.ok(byKey.ppoQty.help.lines.some((line) => line.includes("PPO-2 (50.5 boxes)")))
	assert.equal(byKey.balance.help.formula, "Balance = Cut − Dispatched − Moved to alternative, per lot")
	assert.equal(byKey.balance.help.lines[0], "= 930 pcs − 500 pcs − 0 pcs over the 2 lots with Cut.")
	assert.equal(byKey.cut.foot, "pcs received from Cutting WOs · 4 lots")
})
