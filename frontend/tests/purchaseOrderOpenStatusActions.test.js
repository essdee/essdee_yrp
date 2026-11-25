import assert from "node:assert/strict"
import test from "node:test"

import { openStatusBulkActions } from "../src/departments/fabric-store/purchaseOrderOpenStatusActions.js"

test("Close and Reopen send the selected names and report skips with their reasons", async () => {
	const calls = []
	const setOpenStatus = async (names, close) => {
		calls.push([names, close])
		return { done: ["PO-1"], skipped: [{ name: "PO-2", reason: "Already closed." }] }
	}
	const [close, reopen] = openStatusBulkActions(setOpenStatus)
	assert.deepEqual([close.action, close.label, close.done, close.missed], ["close", "Close", "closed", "skipped"])
	assert.deepEqual([reopen.action, reopen.label, reopen.done], ["reopen", "Reopen", "reopened"])
	const result = await close.run([{ name: "PO-1" }, { name: "PO-2" }])
	assert.deepEqual(result, { done: ["PO-1"], failed: [{ name: "PO-2", error: "Already closed." }] })
	await reopen.run([{ name: "PO-3" }])
	assert.deepEqual(calls, [[["PO-1", "PO-2"], true], [["PO-3"], false]])
})
