import assert from "node:assert/strict"
import test from "node:test"

import { PLANNING_WORKSPACES, visiblePlanningWorkspaces } from "../src/departments/planning/planningViews.js"
import { LOT_VIEW_TABS } from "../src/departments/planning/lot/lotLayout.js"
import { REPORT_COLUMNS, canEditRow, deliveryMessage, reportCell, reviseMessage, revisionRows } from "../src/departments/planning/time-and-action/timeAndAction.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"

test("Planning shows a Time and Action Update card after Lot", () => {
	const keys = PLANNING_WORKSPACES.map((item) => item.key)
	assert.equal(keys.indexOf("time_and_action_update"), keys.indexOf("lots") + 1)
	assert.deepEqual(visiblePlanningWorkspaces({ time_and_action_update: { can_read: true } }).map((item) => item.label), ["Time and Action Update"])
	assert.deepEqual(getWorkspacePaths(departments.find((item) => item.key === "planning")).time_and_action_update, ["/planning/time-and-action-update"])
})

test("Lot view has a Time and Action tab", () => {
	assert.equal(LOT_VIEW_TABS.at(-1).label, "Time and Action")
})

test("delivery impact line matches the Desk wording", () => {
	const data = { delivery_date_before: "2026-11-08", delivery_date_after: "2026-11-15", delivery_days_moved: 6 }
	assert.equal(deliveryMessage(data), "Expected delivery date moves from 08-11-2026 to 15-11-2026 — delayed by 6 working days more")
	assert.equal(deliveryMessage({ ...data, delivery_days_moved: -1 }), "Expected delivery date moves from 08-11-2026 to 15-11-2026 — pulled in by 1 working day")
	assert.equal(deliveryMessage({ ...data, delivery_days_moved: 0 }), "")
})

test("rows are editable only on In Progress T&As by the row's department or Administrator", () => {
	const row = { department: "Cutting" }
	assert.equal(canEditRow({ status: "In Progress", departments: ["Cutting"] }, row), true)
	assert.equal(canEditRow({ status: "In Progress", departments: ["Sewing"] }, row), false)
	assert.equal(canEditRow({ status: "In Progress", departments: [], is_administrator: true }, row), true)
	assert.equal(canEditRow({ status: "Frozen", is_administrator: true }, row), false)
})

test("report view has the 12 Desk columns in order with Desk value mapping", () => {
	assert.deepEqual(REPORT_COLUMNS.map((column) => column.label), [
		"Action", "Department", "Lead Time", "Work Station", "Planned Date", "Freeze Date", "Rescheduled Date",
		"Actual Date", "Planned Delay", "Rescheduled Delay", "Reason", "Performance",
	])
	const row = { actual_date: "2026-11-10", actual_delay: 2, date_diff: 1, performance: 80 }
	const cell = (label) => reportCell(row, REPORT_COLUMNS.find((column) => column.label === label))
	assert.deepEqual([cell("Actual Date"), cell("Planned Delay"), cell("Rescheduled Delay"), cell("Performance")], ["10-11-2026", "2", "1", "80%"])
})

test("revise prompt and revision rows", () => {
	const data = { rows: [{ action: "A", date: "2026-11-02", rescheduled_date: "2026-11-05" }], revisions: { A: ["2026-11-01"] } }
	assert.equal(reviseMessage(data), "Dispatch date changes from 02-11-2026 to 05-11-2026. Revise the dates?")
	assert.deepEqual(revisionRows(data), [{ label: "Rescheduled Date 1", values: ["2026-11-01"] }])
})
