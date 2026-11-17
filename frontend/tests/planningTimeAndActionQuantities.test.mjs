import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import {
	QUANTITY_LABELS, percentOfCut, quantityGrid, quantityLines, usedSizes,
} from "../src/departments/planning/time-and-action/actionQuantities.js"
import { sizeTable } from "../src/utils/lotProcessFlow.js"

const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

const rows = [
	{ colour: "Maroon", part: "", size: "80 cm", cut: 360, delivered: 360, received: 342 },
	{ colour: "Maroon", part: "", size: "90 cm", cut: 1140, delivered: 1140, received: 1083 },
	{ colour: "Navy", part: "Top", size: "80 cm", cut: 100, delivered: 50, received: 0 },
]

test("quantity rows become one Lot page grid row per colour and part, cut as planned", () => {
	assert.deepEqual(quantityGrid(rows), [
		{ colour: "Maroon", part: "", planned: { "80 cm": 360, "90 cm": 1140 }, delivered: { "80 cm": 360, "90 cm": 1140 }, received: { "80 cm": 342, "90 cm": 1083 } },
		{ colour: "Navy", part: "Top", planned: { "80 cm": 100 }, delivered: { "80 cm": 50 }, received: { "80 cm": 0 } },
	])
	assert.deepEqual(quantityGrid(undefined), [])
})

test("pop-up uses the Lot page sizeTable with Cut as the planned label; cutting has no delivered line", () => {
	const table = sizeTable(quantityGrid(rows), ["80 cm", "90 cm"], quantityLines(false), QUANTITY_LABELS)
	assert.deepEqual(table.rows[0].lines.map((line) => line.label), ["Cut", "Delivered", "Received", "Difference"])
	assert.equal(table.rows[0].lines[1].total.tone, "ok")
	assert.equal(table.rows[1].lines[2].total.tone, "none")
	assert.ok(table.footer)
	assert.deepEqual(quantityLines(true), ["planned", "received", "difference"])
})

test("only sizes with rows are shown, in IPD order; percent reads of cut", () => {
	assert.deepEqual(usedSizes(["75 cm", "80 cm", "85 cm", "90 cm"], rows), ["80 cm", "90 cm"])
	assert.equal(percentOfCut(95), "95% of cut")
	assert.equal(percentOfCut(null), "")
})

test("action name is a hover and focus trigger for process actions only, loaded lazily once", () => {
	const table = source("departments/planning/time-and-action/TimeAndActionTable.vue")
	const popup = source("departments/planning/time-and-action/ActionQuantities.vue")
	const editor = source("departments/planning/time-and-action/TimeAndActionEditor.vue")
	const api = source("api/timeAndAction.js")
	assert.match(table, /<ActionQuantities v-if="row.process_name" :time-and-action="timeAndAction" :action="row.action" :process="row.process_name">/)
	assert.match(editor, /<TimeAndActionTable :time-and-action="name"/)
	assert.match(popup, /tabindex="0"[^>]*@mouseenter="open" @mouseleave="scheduleHide" @focus="open" @blur="scheduleHide"/)
	assert.match(popup, /if \(!entry.value.result && !entry.value.loading\) load\(entry.value\)/)
	assert.match(popup, /pi pi-spin pi-spinner/)
	assert.match(popup, /<LotSizeTable /)
	assert.match(api, /process_quantities\.get_action_process_quantities", \{ time_and_action: timeAndAction, action \}/)
})

test("stepper cards of process actions open the same pop-up instead of the native title", () => {
	const stepper = source("departments/planning/time-and-action/TimeAndActionStepper.vue")
	const popup = source("departments/planning/time-and-action/ActionQuantities.vue")
	const editor = source("departments/planning/time-and-action/TimeAndActionEditor.vue")
	assert.match(stepper, /:title="row.process_name \? undefined :/)
	assert.match(stepper, /:is="row.process_name \? ActionQuantities : 'div'" v-bind="row.process_name \? \{ timeAndAction, action: row.action, process: row.process_name, block: true \}/)
	assert.match(editor, /<TimeAndActionStepper :time-and-action="name" :rows="rows" \/>/)
	assert.match(popup, /const cache = new Map\(\)/)
	assert.match(popup, /getEntry\(props.timeAndAction, props.action\)/)
	assert.match(popup, /if \(hideOpen && hideOpen !== hide\) hideOpen\(\)/)
})
