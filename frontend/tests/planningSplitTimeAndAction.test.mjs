import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { getDatedActions, mergeLotOptions, setActualCopied, splitCopyNote } from "../src/departments/planning/time-and-action/splitTimeAndAction.js"

const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

const ROWS = [
	{ action: "YARN", actual_date: "2026-11-04", depends_on: {} },
	{ action: "TRIMS", actual_date: "2026-11-03", depends_on: {} },
	{ action: "KNIT", actual_date: "2026-11-09", depends_on: { YARN: "2026-11-04" } },
	{ action: "CUT", actual_date: "2026-11-10", depends_on: { KNIT: "2026-11-09", TRIMS: "2026-11-03" } },
	{ action: "PACK", actual_date: null, depends_on: { CUT: "2026-11-10" } },
]

test("split lists only actions with an actual date", () => {
	assert.deepEqual(getDatedActions(ROWS).map((row) => row.action), ["YARN", "TRIMS", "KNIT", "CUT"])
})

test("unticking an action also unticks its dated dependents", () => {
	const all = ["YARN", "TRIMS", "KNIT", "CUT"]
	assert.deepEqual(setActualCopied(ROWS, all, "CUT", false), { copied: ["YARN", "TRIMS", "KNIT"], also: [] })
	assert.deepEqual(setActualCopied(ROWS, all, "YARN", false), { copied: ["TRIMS"], also: ["KNIT", "CUT"] })
})

test("ticking an action also ticks its dated dependencies", () => {
	assert.deepEqual(setActualCopied(ROWS, ["TRIMS"], "CUT", true), { copied: ["YARN", "TRIMS", "KNIT", "CUT"], also: ["YARN", "KNIT"] })
	assert.deepEqual(setActualCopied(ROWS, [], "TRIMS", true), { copied: ["TRIMS"], also: [] })
})

test("the note names the actions that changed too", () => {
	assert.equal(splitCopyNote("PPM", false, ["CUTTING"]), "Also unticked CUTTING: it depends on PPM.")
	assert.equal(splitCopyNote("YARN", false, ["KNIT", "CUT"]), "Also unticked KNIT, CUT: they depend on YARN.")
	assert.equal(splitCopyNote("CUT", true, ["YARN", "KNIT"]), "Also ticked YARN, KNIT: CUT depends on them.")
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
	assert.match(api, /\$\{SPLIT\}\.split_time_and_action`, \{ time_and_action: timeAndAction, lots: JSON.stringify\(lots\), skipped_actions: JSON.stringify\(skippedActions\) \}/)
	const dialog = source("departments/planning/time-and-action/SplitTimeAndActionDialog.vue")
	assert.match(dialog, /@filter="search"/)
	assert.match(dialog, /splitTimeAndAction\(props.timeAndAction, selected.value, skippedActions.value\)/)
})

test("split dialog has no help paragraphs and ticks every dated action by default", () => {
	const dialog = source("departments/planning/time-and-action/SplitTimeAndActionDialog.vue")
	assert.doesNotMatch(dialog, /help-text=|ta-split__info|severity="warn"/)
	assert.match(dialog, /copied.value = datedActions.value.map\(\(row\) => row.action\)/)
	assert.match(dialog, /formatDisplayDate\(row.actual_date\)/)
})
