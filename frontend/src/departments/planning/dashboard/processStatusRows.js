import { stepReportContext } from "../../../utils/lotProcessFlow.js"
import { percentOf } from "./dashboardFormat.js"
import { groupDashboardRows } from "./dashboardRows.js"
import { processMeasure } from "./trackingRows.js"

export const NOT_IN_IPD = "-"
export const CELL_TONES = { Completed: "green", "In Progress": "amber", "Not Started": "blue", Draft: "process", "No Work Order": "neutral" }

/** {PPO: status} — the furthest-behind open lot over every Dashboard lot of the PPO. */
export function ppoStatuses(lots) {
	return Object.fromEntries(groupDashboardRows(lots).map((group) => [group.ppo, group.status]))
}

/** Dashboard lot rows with their PPO status and `{process: cell}` from the Process Status endpoint. */
export function processStatusRows(dashboard, status) {
	const ppos = ppoStatuses(dashboard.lots || [])
	return (dashboard.lots || []).map((row) => ({ ...row, ppoStatus: ppos[row.ppo], cells: status.lots?.[row.lot] || {} }))
}

/** Process columns with a cell in any of `rows`, kept in the server's production order. */
export function visibleProcesses(processes, rows) {
	return processes.filter((process) => rows.some((row) => row.cells[process.name]))
}

/** Received % over the cell's submitted processes (packing against lot pcs), as PPO Tracking measures it. */
function receivedPercent(row, steps) {
	const measures = steps.map((step) => processMeasure(row, step))
	const reference = measures.reduce((total, measure) => total + (Number(measure.reference) || 0), 0)
	return Math.round(percentOf(measures.reduce((total, measure) => total + (Number(measure.received) || 0), 0), reference))
}

export function cellView(row, process) {
	const cell = row.cells[process]
	if (!cell) return { label: NOT_IN_IPD, tone: "none", percent: null, isClickable: false }
	const steps = cell.steps || []
	return {
		label: cell.status,
		tone: CELL_TONES[cell.status] || "neutral",
		percent: cell.status === "In Progress" && steps.length ? receivedPercent(row, steps) : null,
		isClickable: steps.length > 0,
	}
}

/** Note under the hover card header for cells whose Work Orders are missing or still drafts. */
export function cellNote(cell) {
	if (!cell) return "Not in this lot's IPDs."
	if (cell.drafts) return `${cell.drafts} draft Work Order${cell.drafts === 1 ? "" : "s"}, not submitted yet.`
	return cell.steps?.length ? "" : "No Work Order for this process yet."
}

/** Lot page report context of a cell: its first Work Order process, or the IPD process before any Work Order; null outside the IPD. */
export function cellReportContext(row, process, cell) {
	if (!cell) return null
	const step = cell.steps?.[0] || { name: process, work_orders: [] }
	return stepReportContext(row.lot, row.item, step.name, step.work_orders)
}
