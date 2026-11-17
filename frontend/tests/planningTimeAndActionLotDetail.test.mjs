import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { getLotDetailScope, getRevertMessage, removeFromQueue } from "../src/departments/planning/time-and-action/timeAndAction.js"

const taSource = (file) => readFileSync(new URL(`../src/departments/planning/time-and-action/${file}`, import.meta.url), "utf8")

test("Lot Detail scope: a Lot T&A asks PPO Tracking for its lot, a PO T&A for every lot of the PO", () => {
	assert.deepEqual(getLotDetailScope("SD YRP Lot", "F0926-46/1"), { ppos: [], lots: ["F0926-46/1"] })
	assert.deepEqual(getLotDetailScope("YRP Production Order", "PPO-00291"), { ppos: ["PPO-00291"], lots: [] })
})

test("header shows a Lot Detail button to readers with tracking access, after Split T&A", () => {
	const header = taSource("TimeAndActionHeader.vue")
	const button = header.match(/<Button v-if="data.can_view_lot_detail" label="Lot Detail"[^>]*>/)?.[0]
	assert.ok(button)
	assert.doesNotMatch(button, /:disabled/)
	assert.match(button, /emit\('lot-detail'\)/)
	assert.ok(header.indexOf('label="Split T&A"') < header.indexOf('label="Lot Detail"'))
	assert.match(header, /defineEmits\(\[[^\]]*"lot-detail"/)
})

test("editor opens the Lot Detail dialog with the T&A's against", () => {
	const editor = taSource("TimeAndActionEditor.vue")
	assert.match(editor, /@lot-detail="lotDetailVisible = true"/)
	assert.match(editor, /<LotDetailDialog v-if="data" v-model:visible="lotDetailVisible" :against="data.against" :against-id="data.against_id" \/>/)
})

test("Lot Detail dialog reuses the PPO Tracking endpoint and lot panel, one tab per lot", () => {
	const dialog = taSource("LotDetailDialog.vue")
	assert.match(dialog, /getPpoTracking\(scope\.value\.ppos, scope\.value\.lots\)/)
	assert.match(dialog, /import TrackingLotDetail from "\.\.\/dashboard\/TrackingLotDetail\.vue"/)
	assert.match(dialog, /<TrackingLotDetail :row="row" :reports="reports" \/>/)
	assert.match(dialog, /<TabList v-if="data\.lots\.length > 1">/)
	assert.match(dialog, /class="erp-dialog--xl ta-lot-detail"/)
	assert.match(dialog, /\.ta-lot-detail\.p-dialog \{ width: 100vw;/)
	assert.match(dialog, /formatDisplayDate\(row\.delivery/)
})

test("T&A ids are plain text in /web: no Desk link to SD YRP Time and Action", () => {
	for (const file of ["TimeAndActionHeader.vue", "TimeAndActionQueue.vue", "LotTimeAndActionTab.vue", "ProductionOrderTimeAndActionTab.vue", "SplitTimeAndActionDialog.vue", "ConvertToLotTimeAndActionDialog.vue"]) {
		assert.doesNotMatch(taSource(file), /SD YRP Time and Action|sd-yrp-time-and-action|DocumentLink/, file)
	}
	assert.match(taSource("LotTimeAndActionTab.vue"), /<dd data-ta-name>\{\{ data\.name \}\}<\/dd>/)
	assert.match(taSource("LotTimeAndActionTab.vue"), /label="Update dates"/)
})

test("revert confirmation names the T&A and who can create a new one", () => {
	assert.equal(getRevertMessage("TA-2026-00007", "Lot"), "This deletes TA-2026-00007 and all its dates. The Lot can then create a new T&A.")
	assert.match(getRevertMessage("TA-1", "Production Order"), /The Production Order can then/)
})

test("reverting removes the T&A from the queue and opens the next, else the previous, else none", () => {
	const rows = [{ name: "TA-1" }, { name: "TA-2" }, { name: "TA-3" }]
	assert.deepEqual(removeFromQueue(rows, "TA-2"), { rows: [{ name: "TA-1" }, { name: "TA-3" }], next: "TA-3" })
	assert.equal(removeFromQueue(rows, "TA-3").next, "TA-2")
	assert.deepEqual(removeFromQueue([{ name: "TA-1" }], "TA-1"), { rows: [], next: "" })
})

test("Revert T&A is one shared button gated by can_revert, used by the header and both tabs", () => {
	const button = taSource("RevertTimeAndActionButton.vue")
	assert.match(button, /<template v-if="data\.can_revert">/)
	assert.match(button, /severity="danger"/)
	assert.match(button, /revertTimeAndAction\(name\)/)
	assert.match(button, /toast\.add\(\{ severity: "success"/)
	assert.match(button, /emit\("reverted", name\)/)
	const header = taSource("TimeAndActionHeader.vue")
	assert.ok(header.indexOf('label="Complete T&A"') < header.indexOf("<RevertTimeAndActionButton"))
	assert.match(taSource("TimeAndActionEditor.vue"), /@reverted="emit\('reverted', \$event\)"/)
	assert.match(taSource("TimeAndActionUpdate.vue"), /@reverted="reverted"/)
	assert.match(taSource("TimeAndActionUpdate.vue"), /removeFromQueue\(rows\.value, name\)/)
	const tab = taSource("LotTimeAndActionTab.vue")
	assert.ok(tab.indexOf('<slot name="actions"') < tab.indexOf("<RevertTimeAndActionButton"))
	assert.match(taSource("ProductionOrderTimeAndActionTab.vue"), /@reverted="emit\('changed'\)"/)
	assert.match(readFileSync(new URL("../src/departments/planning/lot/LotPage.vue", import.meta.url), "utf8"), /@reverted="timeAndAction\.changed"/)
	assert.match(readFileSync(new URL("../src/api/timeAndAction.js", import.meta.url), "utf8"), /revert_time_and_action`, \{ time_and_action: timeAndAction \}/)
})
