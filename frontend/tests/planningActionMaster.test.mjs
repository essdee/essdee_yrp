import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import {
	ACTION_MASTER_KINDS, actionMasterPayload, dependencyOptions, headerValues, moveStep, newStep, pruneDependencies, removeStep, stepsFromDoc, stepTables,
} from "../src/departments/planning/action-master/actionMaster.js"
import { PLANNING_WORKSPACES, visiblePlanningWorkspaces } from "../src/departments/planning/planningViews.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"
import { webDocumentPath } from "../src/router/webDocumentRoutes.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const step = (action, dependent_action = [], lead_time = 2) => newStep({ action, lead_time, department: "Cutting", dependent_action })
const actions = (steps) => steps.map((row) => row.action)

const master = {
	description: "Knits", min_qty: 0, max_qty: 500, quantity: "0 - 500",
	details: [
		{ action: "FABRIC", lead_time: 3, department: "Purchase", target: 0 },
		{ action: "CUTTING", lead_time: 2, department: "Cutting", target: 0 },
		{ action: "SEWING", lead_time: 5, department: "Sewing", target: 0 },
	],
	action_master_dependent_details: [
		{ action: "CUTTING", dependent_action: "FABRIC" },
		{ action: "SEWING", dependent_action: "FABRIC" },
		{ action: "SEWING", dependent_action: "CUTTING" },
	],
}

test("Planning shows an Action Master card after Time and Action Update, gated by Action Master read", () => {
	const keys = PLANNING_WORKSPACES.map((item) => item.key)
	assert.equal(keys.indexOf("action_masters"), keys.indexOf("time_and_action_update") + 1)
	assert.deepEqual(visiblePlanningWorkspaces({ action_masters: { can_read: true } }).map((item) => item.to), ["/planning/action-masters"])
	assert.deepEqual(visiblePlanningWorkspaces({ action_masters: { can_read: false } }), [])
	const planning = departments.find((department) => department.key === "planning")
	assert.equal(getWorkspacePaths(planning).action_masters.includes("/planning/action-masters"), true)
})

test("Action Master links open the Planning page", () => {
	assert.equal(webDocumentPath("SD YRP Action Master", "Master-00072", "/web/planning/action-masters"), "/web/planning/action-masters/Master-00072")
	const router = source("../src/router/index.js")
	assert.match(router, /path: "\/planning\/action-masters\/new", name: PLANNING_ROUTES\.actionMasterNew/)
	assert.match(router, /path: "\/planning\/action-masters\/:documentName", name: PLANNING_ROUTES\.actionMaster, component: PlanningActionMasterPage, props: \(route\) => \(\{ kind: "master"/)
	assert.match(router, /path: "\/planning\/action-master-templates\/:documentName", name: PLANNING_ROUTES\.actionMasterTemplate, component: PlanningActionMasterPage, props: \(route\) => \(\{ kind: "template"/)
	assert.equal(webDocumentPath("SD YRP Action Master Template", "Master Template-00001", "/web/planning"), "/web/planning/action-master-templates/Master%20Template-00001")
})

test("a stored master round-trips into steps and back into the child tables Desk stores", () => {
	const steps = stepsFromDoc(master)
	assert.deepEqual(steps.map(({ action, dependent_action }) => [action, dependent_action]), [["FABRIC", []], ["CUTTING", ["FABRIC"]], ["SEWING", ["FABRIC", "CUTTING"]]])
	assert.deepEqual(stepTables(steps), { details: master.details, action_master_dependent_details: master.action_master_dependent_details })
})

test("blank rows are not saved and a blank department is stored as null", () => {
	const tables = stepTables([newStep({ action: "PACKING", lead_time: 1 }), newStep()])
	assert.deepEqual(tables.details, [{ action: "PACKING", lead_time: 1, department: null, target: 0 }])
})

test("a step can only depend on actions above it", () => {
	const steps = [step("FABRIC"), step(""), step("CUTTING"), step("SEWING")]
	assert.deepEqual(dependencyOptions(steps, 0), [])
	assert.deepEqual(dependencyOptions(steps, 3), ["FABRIC", "CUTTING"])
})

test("moving or removing a step drops dependencies that would point below it", () => {
	const steps = [step("FABRIC"), step("CUTTING", ["FABRIC"]), step("SEWING", ["FABRIC", "CUTTING"])]
	const moved = moveStep(steps, 2, 1)
	assert.deepEqual(actions(moved), ["FABRIC", "SEWING", "CUTTING"])
	assert.deepEqual(moved[1].dependent_action, ["FABRIC"])
	assert.deepEqual(moved[2].dependent_action, ["FABRIC"])
	assert.equal(moveStep(steps, 0, -1), steps)
	assert.deepEqual(removeStep(steps, 0).map((row) => row.dependent_action), [[], ["CUTTING"]])
	const renamed = pruneDependencies([step("DYEING"), steps[1]])
	assert.deepEqual(renamed[1].dependent_action, [])
})

test("an amended draft copies the header and steps and points at the cancelled master", () => {
	const payload = actionMasterPayload(headerValues(ACTION_MASTER_KINDS.master.headerFields, master), stepsFromDoc(master), "Master-00072")
	assert.equal(payload.amended_from, "Master-00072")
	assert.equal(payload.max_qty, 500)
	assert.equal("quantity" in payload, false)
	assert.equal(payload.details.length, 3)
	assert.equal("amended_from" in actionMasterPayload(headerValues(ACTION_MASTER_KINDS.master.headerFields, master), []), false)
})

test("action rows pick SD YRP Actions with create, and fill lead time and department from the picked action", () => {
	const steps = source("../src/departments/planning/action-master/ActionMasterSteps.vue")
	assert.match(steps, /<LinkField v-if="!disabled" :model-value="step\.action" doctype="SD YRP Action"/)
	assert.doesNotMatch(steps, /doctype="SD YRP Action"[^>]*:allow-create="false"/)
	assert.match(steps, /getDoc\("SD YRP Action", name\)/)
	assert.match(steps, /update\(index, \{ action: name, lead_time: action\?\.lead_time \?\? null, department: action\?\.department \|\| "" \}\)/)
})

test("the page submits, cancels and amends only with the matching document permission", () => {
	const page = source("../src/departments/planning/action-master/ActionMasterPage.vue")
	assert.match(page, /doc\.value\.docstatus === 1 && Boolean\(permissions\.value\?\.cancel\)/)
	assert.match(page, /doc\.value\.docstatus === 2 && Boolean\(permissions\.value\?\.amend\)/)
	assert.match(page, /query: \{ amend_from: name \}/)
})

test("the Action Master Template field only picks existing templates, it never quick-creates one", () => {
	const page = source("../src/departments/planning/action-master/ActionMasterPage.vue")
	assert.match(page, /<LinkField v-if="field\.fieldname === 'action_master_template'"[^>]*:allow-create="false"/)
	assert.match(page, /<FormField v-else /)
})

test("Planning shows an Action Master Template card after Action Master", () => {
	const keys = PLANNING_WORKSPACES.map((item) => item.key)
	assert.equal(keys.indexOf("action_master_templates"), keys.indexOf("action_masters") + 1)
	assert.deepEqual(visiblePlanningWorkspaces({ action_master_templates: { can_read: true } }).map((item) => item.to), ["/planning/action-master-templates"])
})

test("templates reuse the master page without lifecycle or template fields", () => {
	const { master, template } = ACTION_MASTER_KINDS
	assert.equal(template.doctype, "SD YRP Action Master Template")
	assert.deepEqual(template.headerFields, master.headerFields.filter((field) => !["action_master_template", "disable"].includes(field)))
	assert.equal(template.listPath, "/planning/action-master-templates")
	const page = source("../src/departments/planning/action-master/ActionMasterPage.vue")
	assert.match(page, /:show-submit="isMaster && Boolean\(permissions\?\.submit\)"/)
	assert.match(page, /<ActionMasterSteps v-model:steps="steps"/)
})

test("master and template pages show the inline Back link to their list, with list stepping on saved records", () => {
	const page = source("../src/departments/planning/action-master/ActionMasterPage.vue")
	assert.match(page, /<DepartmentPage :title="config\.label" :back-to="config\.listPath" :back-label="config\.pluralLabel"[^>]*inline-navigation>/)
	assert.match(page, /<InlinePageNavigation title-target="action-master-title" :show-document-navigation="Boolean\(doc\.name\)"/)
})
