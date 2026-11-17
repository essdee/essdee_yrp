import assert from "node:assert/strict"
import test from "node:test"

import { PLANNING_WORKSPACES, visiblePlanningWorkspaces } from "../src/departments/planning/planningViews.js"
import { LOT_VIEW_TABS } from "../src/departments/planning/lot/lotLayout.js"
import { readFileSync } from "node:fs"

import {
	REPORT_COLUMNS, STEP_LABELS, againstLabel, againstShortLabel, canEditRow, countStatuses, getBlockedBy, getDelay, getImpact, getPendingSummary,
	getReviseMessage, getRowStatus, getRunningDelay, getSaveMessage, reportCell, reportTone,
} from "../src/departments/planning/time-and-action/timeAndAction.js"
import {
	describeActionChanges, getDependsOn, getDependsOnOptions, getEditDependsOnOptions, getInsertSlots, getLastDatedIndex,
	getRemovableActions, getRequiredByOptions, pruneEditsForRemove, setDependencyEdit,
} from "../src/departments/planning/time-and-action/timeAndActionSteps.js"
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

test("save bar impact line comes from preview_actual_dates in working days", () => {
	const data = { delivery_date_before: "2026-12-19", delivery_date_after: "2026-12-22", delivery_days_moved: 2 }
	assert.deepEqual(getImpact(data, true), { tone: "late", from: "19-12-2026", to: "22-12-2026", text: "+2 working days" })
	assert.deepEqual(getImpact({ ...data, delivery_days_moved: -1 }, true), { tone: "early", from: "19-12-2026", to: "22-12-2026", text: "1 working day earlier" })
	assert.equal(getImpact({ ...data, delivery_days_moved: 0 }, true).text, "No change to expected delivery")
	assert.equal(getImpact({}, false).text, "Enter actual dates to see the effect on delivery")
	assert.equal(getSaveMessage(data), "Expected delivery moves 19-12-2026 to 22-12-2026, +2 working days.")
	assert.equal(getSaveMessage({ delivery_date_before: "2026-12-19", delivery_days_moved: 0 }), "Expected delivery stays 19-12-2026.")
})

test("row status chips derive from server rows: done, blocked, overdue, due, error", () => {
	const today = "2026-11-16"
	assert.equal(getRowStatus({ actual_date: "2026-11-10", rescheduled_date: "2026-11-12" }, { today }), "done")
	const blocked = { rescheduled_date: "2026-11-20", depends_on: { CUTTING: null, TRIMS: "2026-11-10" } }
	assert.equal(getRowStatus(blocked, { today }), "blocked")
	assert.deepEqual(getBlockedBy(blocked), ["CUTTING"])
	assert.equal(getRowStatus({ rescheduled_date: "2026-11-14", depends_on: {} }, { today }), "overdue")
	assert.equal(getRowStatus({ rescheduled_date: "2026-11-17", depends_on: {} }, { today }), "due")
	assert.equal(getRowStatus({ actual_date: "2026-11-10" }, { today, hasError: true }), "error")
	assert.deepEqual(countStatuses(["done", "done", "blocked", "due"]), { done: 2, due: 1, overdue: 0, blocked: 1, error: 0 })
})

test("delay cell uses Rescheduled Delay with Planned Delay underneath; negative is late", () => {
	assert.deepEqual(getDelay({ actual_date: "2026-11-14", date_diff: -2, actual_delay: -7 }), { text: "2 days late", tone: "late", planned: -7 })
	assert.deepEqual(getDelay({ actual_date: "2026-11-14", date_diff: 0, actual_delay: 0 }), { text: "On time", tone: "ok", planned: 0 })
	assert.deepEqual(getDelay({ actual_date: "2026-11-14", date_diff: 1, actual_delay: 1 }), { text: "1 day early", tone: "ok", planned: 1 })
	assert.equal(getDelay({ actual_date: null }), null)
})

test("save bar pending summary", () => {
	assert.deepEqual(getPendingSummary({ changes: 1, errors: 0, missingReasons: 1 }), ["1 unsaved change", "1 reason missing"])
	assert.deepEqual(getPendingSummary({ changes: 2, errors: 1 }), ["2 unsaved changes", "1 date to fix"])
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

test("revise prompt names the dispatch date change", () => {
	const data = { rows: [{ action: "A", date: "2026-11-02", rescheduled_date: "2026-11-05" }] }
	assert.match(getReviseMessage(data), /Dispatch date changes from 02-11-2026 to 05-11-2026\.$/)
})

test("report view colours negative delays red and positive green", () => {
	const column = REPORT_COLUMNS.find((item) => item.label === "Planned Delay")
	assert.deepEqual([-2, 0, 1].map((value) => reportTone({ actual_delay: value }, column)), ["neg", "", "pos"])
	assert.equal(reportTone({ reason: "x" }, REPORT_COLUMNS.find((item) => item.label === "Reason")), "")
})

const taSource = (file) => readFileSync(new URL(`../src/departments/planning/time-and-action/${file}`, import.meta.url), "utf8")

test("update page is a split view: queue on the left, the ?ta= T&A in the cockpit", () => {
	const page = taSource("TimeAndActionUpdate.vue")
	assert.match(page, /<TimeAndActionQueue v-model:lot="filters.lot" v-model:item="filters.item"/)
	assert.match(page, /<TimeAndActionEditor v-if="selected" :key="selected" :name="selected"/)
	assert.match(page, /selected = ref\(route.query.ta \|\| ""\)/)
	assert.match(page, /query: \{ \.\.\.route\.query, ta: name \|\| undefined \}/)
	assert.match(page, /Discard changes to \$\{selected\}\?/)
	assert.doesNotMatch(page, /ta-list__expand|toggle\(/)
	assert.match(taSource("LotTimeAndActionTab.vue"), /query: \{ lot: lot \|\| undefined, ta: data.name \}/)
})

test("queue cards show the T&A, running delay chip, item, Lot or PO and dated progress", () => {
	const queue = taSource("TimeAndActionQueue.vue")
	assert.match(queue, /Open T&A Queue/)
	assert.match(queue, /getRunningDelay\(row\.delay\)\.tone === 'late' \? 'late' : 'ok'/)
	assert.match(queue, /<strong class="ta-card__against">\{\{ againstShortLabel\(row\.against\) \}\} \{\{ row\.against_id \}\}<\/strong>/)
	assert.match(queue, /<span class="ta-card__name">\{\{ row\.name \}\}<\/span>/)
	assert.match(queue, /\{\{ row\.dated \}\} of \{\{ row\.total \}\} dated/)
	assert.match(queue, /'is-selected': row\.name === selected/)
})

test("cockpit table has the split-view columns and keeps the date logic", () => {
	const table = taSource("TimeAndActionTable.vue")
	assert.match(table, /<th>Action<\/th><th>Planned \/ Freeze<\/th><th>Rescheduled<\/th><th>Actual Date<\/th><th>Reason<\/th><th class="ta-acts__right">Delay<\/th>/)
	assert.match(table, /P: \{\{ formatDisplayDate\(row\.planned_start_date, ""\) \}\}/)
	assert.match(table, /F: \{\{ formatDisplayDate\(row\.date, ""\) \}\}/)
	assert.match(table, /\{\{ row\.lead_time \}\}d lead/)
	assert.match(table, /Waiting for \{\{ row\.blockedBy\.join\(", "\) \}\}/)
	assert.match(table, /v-if="row\.auto_actual_date && !row\.edited"/)
	assert.match(table, /<InputText v-if="row\.editable"/)
	assert.match(table, /row\.late \? 'Why late\? Required' : 'Remarks \(optional\)'/)
	assert.doesNotMatch(table, /Not needed/)
	assert.doesNotMatch(table, /Rescheduled Details|ta-matrix|<th>Status<\/th>/)
	assert.match(taSource("TimeAndActionEditor.vue"), /@actual="setActual" @reason="setReason"/)
	const stepper = taSource("TimeAndActionStepper.vue")
	assert.match(stepper, /STEP \{\{ row\.index \+ 1 \}\}/)
	assert.match(stepper, /row\.actual_date \|\| row\.rescheduled_date/)
})

test("stepper labels and short Against labels", () => {
	assert.deepEqual(STEP_LABELS, { done: "Done", due: "Due", overdue: "Overdue", blocked: "Locked", error: "Check date" })
	assert.deepEqual(["SD YRP Lot", "YRP Production Order"].map(againstShortLabel), ["Lot", "PO"])
})

test("Against column shows the Desk label of the T&A's against DocType", () => {
	assert.deepEqual(["SD YRP Lot", "YRP Production Order"].map(againstLabel), ["Lot", "Production Order"])
})

test("running delay reads the T&A delay in working days; negative is late", () => {
	assert.deepEqual(getRunningDelay(-5), { tone: "late", text: "5 working days late" })
	assert.deepEqual(getRunningDelay(1), { tone: "ok", text: "1 working day early" })
	assert.deepEqual(getRunningDelay(0), { tone: "none", text: "On schedule" })
	assert.match(taSource("TimeAndActionQueue.vue"), /getRunningDelay\(row\.delay\)\.text/)
})

const STEP_ROWS = [
	{ action: "PLANNING", actual_date: "2026-11-02" },
	{ action: "YARN", actual_date: null },
	{ action: "CUTTING", actual_date: "2026-11-05" },
	{ action: "SEWING", actual_date: null },
	{ action: "PACKING", actual_date: null },
]

test("Update Action offers slots only after the last completed action", () => {
	assert.equal(getLastDatedIndex(STEP_ROWS), 2)
	assert.deepEqual(getInsertSlots(STEP_ROWS).map((slot) => slot.label), ["After CUTTING", "After SEWING", "After PACKING (last)"])
	assert.deepEqual(getInsertSlots([{ action: "A" }]).map((slot) => slot.value), [null, "A"])
	assert.deepEqual(getRemovableActions(STEP_ROWS), ["YARN", "SEWING", "PACKING"])
})

test("Update Action dependency options: depends on anything above, must finish before only undated below", () => {
	assert.deepEqual(getDependsOnOptions(STEP_ROWS, "SEWING"), ["PLANNING", "YARN", "CUTTING", "SEWING"])
	assert.deepEqual(getRequiredByOptions(STEP_ROWS, "CUTTING"), ["SEWING", "PACKING"])
	assert.deepEqual(getRequiredByOptions(STEP_ROWS, "PACKING"), [])
})

test("header titles the T&A by its Lot or PO id and shows the T&A id small", () => {
	const header = taSource("TimeAndActionHeader.vue")
	assert.match(header, /<h2><span class="ta-head__kind">\{\{ againstShortLabel\(data\.against\) \}\}<\/span> \{\{ data\.against_id \}\}<\/h2>/)
	assert.match(header, /<span class="ta-head__name" title="T&A ID">\{\{ data\.name \}\}<\/span>/)
	assert.doesNotMatch(header, /<h2>\{\{ data\.name \}\}/)
})

test("Update Action summary lists every add and remove", () => {
	const adds = [{ action: "PRINTING", lead_time: 3, depends_on: ["CUTTING"], required_by: ["SEWING"] }]
	assert.deepEqual(describeActionChanges(adds, ["YARN"]), ["Remove YARN", "Add PRINTING (3 days) after CUTTING; before SEWING"])
	const header = taSource("TimeAndActionHeader.vue")
	assert.match(header, /label="Update Action"/)
	assert.match(header, /v-if="data\.can_edit_steps"/)
	assert.doesNotMatch(header, /label="(Add|Remove) Action"/)
	assert.match(header, /getRunningDelay\(props\.data\.delay\)/)
})

const EDIT_ROWS = [
	{ action: "CUTTING", actual_date: "2026-11-05", depends_on: {} },
	{ action: "PRINTING", actual_date: null, depends_on: { CUTTING: "2026-11-05" } },
	{ action: "SEWING", actual_date: null, depends_on: { CUTTING: "2026-11-05" } },
]

test("Edit Dependencies offers only actions above the row", () => {
	assert.deepEqual(getEditDependsOnOptions(EDIT_ROWS, "SEWING"), ["CUTTING", "PRINTING"])
	assert.deepEqual(getEditDependsOnOptions(EDIT_ROWS, "CUTTING"), [])
	assert.deepEqual(getDependsOn(EDIT_ROWS[2]), ["CUTTING"])
})

test("Edit Dependencies keeps one edit per action and drops edits back to the original", () => {
	let edits = setDependencyEdit([], EDIT_ROWS, "SEWING", ["CUTTING", "PRINTING"])
	assert.deepEqual(edits, [{ action: "SEWING", depends_on: ["CUTTING", "PRINTING"] }])
	edits = setDependencyEdit(edits, EDIT_ROWS, "SEWING", ["PRINTING"])
	assert.deepEqual(edits, [{ action: "SEWING", depends_on: ["PRINTING"] }])
	assert.deepEqual(setDependencyEdit(edits, EDIT_ROWS, "SEWING", ["CUTTING"]), [])
})

test("Removing an action prunes it from pending dependency edits", () => {
	const edits = [{ action: "SEWING", depends_on: ["CUTTING", "PRINTING"] }, { action: "PRINTING", depends_on: [] }]
	assert.deepEqual(pruneEditsForRemove(edits, "PRINTING"), [{ action: "SEWING", depends_on: ["CUTTING"] }])
})

test("Update Action summary lists dependency edits", () => {
	const edits = [{ action: "SEWING", depends_on: ["CUTTING", "PRINTING"] }, { action: "PACKING", depends_on: [] }]
	assert.deepEqual(describeActionChanges([], [], edits), ["Change SEWING dependencies → CUTTING, PRINTING", "Change PACKING dependencies → none"])
	const dialog = readFileSync(new URL("../src/departments/planning/time-and-action/UpdateActionsDialog.vue", import.meta.url), "utf8")
	assert.match(dialog, /previewUpdateActions\(props\.name, nextAdds, nextRemoves, nextEdits\)/)
	assert.match(dialog, /updateActions\(props\.name, adds\.value, removes\.value, edits\.value\)/)
})

test("Lot T&A tab asks for an Assigned Person when that blocks creating", () => {
	const tab = taSource("LotTimeAndActionTab.vue")
	assert.match(tab, /v-else-if="createBlockedReason === 'no_assigned_person'"[^>]*>Please set the Assigned Person to create T&A\.<\/Message>/)
	const page = readFileSync(new URL("../src/departments/planning/lot/LotPage.vue", import.meta.url), "utf8")
	assert.match(page, /<LotTimeAndActionTab v-bind="timeAndAction\.tabProps"/)
	assert.match(taSource("useLotTimeAndActionTab.js"), /createBlockedReason: context\.value\?\.create_blocked_reason \|\| ""/)
})
