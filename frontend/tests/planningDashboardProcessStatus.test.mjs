import test from "node:test"
import assert from "node:assert/strict"

import { pendingQuantity } from "../src/departments/planning/dashboard/trackingRows.js"
import { readTrackingQuery, trackingQuery } from "../src/departments/planning/dashboard/routeFilters.js"
import {
	NOT_IN_IPD,
	cellNote,
	cellReportContext,
	cellView,
	ppoStatuses,
	processStatusRows,
	visibleProcesses,
} from "../src/departments/planning/dashboard/processStatusRows.js"

const step = (values) => ({ name: "Cutting", kind: "item", planned: 100, delivered: 0, received: 0, work_orders: [], ...values })
const lots = [
	{ lot: "L-1", ppo: "PPO-1", item: "A", status: "In sewing", status_rank: 500, qty: 100 },
	{ lot: "L-2", ppo: "PPO-1", item: "A", status: "Waiting for cutting", status_rank: 200, qty: 50 },
	{ lot: "L-3", ppo: "PPO-2", item: "B", status: "No Work Order yet", status_rank: 0, qty: 30 },
]
const status = {
	processes: [{ name: "Knitting", kind: "fabric" }, { name: "Cutting", kind: "garment" }, { name: "Printing", kind: "garment" }],
	lots: {
		"L-1": { Knitting: { status: "Completed", steps: [] }, Cutting: { status: "In Progress", steps: [step({ received: 40 })] } },
		"L-2": { Cutting: { status: "No Work Order", steps: [] } },
	},
}

test("the PPO status is its furthest-behind lot over every lot of the PPO", () => {
	assert.deepEqual(ppoStatuses(lots), { "PPO-1": "Waiting for cutting", "PPO-2": "No Work Order yet" })
})

test("rows join Dashboard lots with their process cells and PPO status", () => {
	const rows = processStatusRows({ lots }, status)
	assert.equal(rows[0].ppoStatus, "Waiting for cutting")
	assert.equal(rows[0].cells.Cutting.status, "In Progress")
	assert.deepEqual(rows[2].cells, {})
})

test("only processes used by the shown rows become columns, in server order", () => {
	const rows = processStatusRows({ lots }, status)
	assert.deepEqual(visibleProcesses(status.processes, rows).map((process) => process.name), ["Knitting", "Cutting"])
	assert.deepEqual(visibleProcesses(status.processes, rows.slice(1)).map((process) => process.name), ["Cutting"])
})

test("a process outside the lot IPDs shows a dash; others show a toned label", () => {
	const [row] = processStatusRows({ lots }, status)
	assert.deepEqual(cellView(row, "Printing"), { label: NOT_IN_IPD, tone: "none", percent: null, isClickable: false })
	assert.deepEqual(cellView(row, "Knitting"), { label: "Completed", tone: "green", percent: null, isClickable: false })
	assert.deepEqual(cellView(row, "Cutting"), { label: "In Progress", tone: "amber", percent: 40, isClickable: true })
	assert.equal(cellView(processStatusRows({ lots }, status)[1], "Cutting").tone, "neutral")
})

test("the hover card notes cells without submitted Work Orders", () => {
	assert.equal(cellNote(undefined), "Not in this lot's IPDs.")
	assert.equal(cellNote({ status: "No Work Order", steps: [], drafts: 0 }), "No Work Order for this process yet.")
	assert.equal(cellNote({ status: "Draft", steps: [], drafts: 2 }), "2 draft Work Orders, not submitted yet.")
	assert.equal(cellNote({ status: "In Progress", steps: [step()], drafts: 1 }), "1 draft Work Order, not submitted yet.")
	assert.equal(cellNote({ status: "Completed", steps: [step()], drafts: 0 }), "")
})

test("pending is planned less received, never below zero", () => {
	assert.equal(pendingQuantity({ planned: 100, received: 30 }), 70)
	assert.equal(pendingQuantity({ planned: 100, received: 102 }), 0)
	assert.equal(pendingQuantity({}), 0)
})

test("the Reports context is the Lot page step context of the cell's Work Order process, or its IPD process", () => {
	const row = { lot: "L 1", item: "SHIRT" }
	const group = step({ name: "Ironing and Packing", work_orders: [{ name: "WO-1", supplier: "S-1", wo_date: "2026-10-02" }] })
	assert.deepEqual(cellReportContext(row, "Packing", { status: "In Progress", steps: [group] }), {
		lot: "L 1", item: "SHIRT", process: "Ironing and Packing", supplier: "S-1", from_date: "2026-10-02", lot_date: "",
	})
	assert.equal(cellReportContext(row, "Bottom Fusing", { status: "No Work Order", steps: [] }).process, "Bottom Fusing")
	assert.equal(cellReportContext(row, "Printing", undefined), null)
})

test("the Process Status tab round-trips through the route query", () => {
	assert.equal(readTrackingQuery({ view: "process-status" }).view, "process-status")
	assert.equal(readTrackingQuery({ view: "bogus" }).view, "dashboard")
	assert.equal(trackingQuery({ filters: { ppo: [], lot: [], process: [] }, showDispatched: false }).view, "tracking")
})
