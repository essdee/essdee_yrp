import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { mergeLotOptions, splitConfirmMessage } from "../src/departments/planning/time-and-action/splitTimeAndAction.js"

const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

test("split confirmation names the lots and says the source continues", () => {
	assert.equal(
		splitConfirmMessage("TA-2026-00001", ["LOT-2", "LOT-3"]),
		"Create 2 Lot T&As (LOT-2, LOT-3) as copies of TA-2026-00001: rows, dependencies, work stations, dates, actual dates and reasons. TA-2026-00001 continues and each Lot is updated on its own.",
	)
	assert.match(splitConfirmMessage("TA-1", ["LOT-2"]), /^Create 1 Lot T&A \(LOT-2\)/)
})

test("searching keeps already selected lots in the options", () => {
	const previous = [{ name: "LOT-1", item: "TEE" }, { name: "LOT-2", item: "POLO" }]
	const found = [{ name: "LOT-3", item: "TEE" }, { name: "LOT-1", item: "TEE" }]
	assert.deepEqual(
		mergeLotOptions(previous, found, ["LOT-2"]).map((lot) => lot.name),
		["LOT-2", "LOT-3", "LOT-1"],
	)
	assert.deepEqual(mergeLotOptions([], found, []).map((lot) => lot.name), ["LOT-3", "LOT-1"])
})

test("Lot Time and Action tab offers Split T&A when the server allows it", () => {
	const page = source("departments/planning/lot/LotPage.vue")
	assert.match(page, /<Button v-if="data.can_split" label="Split T&A"/)
	assert.match(page, /<SplitTimeAndActionDialog/)
})

test("Time and Action cockpit header offers Split T&A next to Complete T&A", () => {
	assert.match(source("departments/planning/time-and-action/TimeAndActionHeader.vue"), /<Button v-if="data.can_split" label="Split T&A"/)
	assert.match(source("departments/planning/time-and-action/TimeAndActionEditor.vue"), /<SplitTimeAndActionDialog/)
})

test("split dialog searches eligible lots on the server and sends them as JSON", () => {
	const api = source("api/timeAndAction.js")
	assert.match(api, /const SPLIT = "essdee_yrp.time_and_action.split"/)
	assert.match(api, /\$\{SPLIT\}\.get_split_lots`, \{ time_and_action: timeAndAction, txt: txt \|\| null \}/)
	assert.match(api, /\$\{SPLIT\}\.split_time_and_action`, \{ time_and_action: timeAndAction, lots: JSON.stringify\(lots\) \}/)
	const dialog = source("departments/planning/time-and-action/SplitTimeAndActionDialog.vue")
	assert.match(dialog, /@filter="search"/)
	assert.match(dialog, /splitTimeAndAction\(props.timeAndAction, selected.value\)/)
})
