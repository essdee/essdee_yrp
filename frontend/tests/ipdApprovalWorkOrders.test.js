import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { workOrderGroups } from "../src/departments/merch/ipd/approval/ipdApproval.js"

const order = (name, process_name, is_affected = false) => ({ name, process_name, is_affected })

test("work orders group by process with changed processes first", () => {
	const groups = workOrderGroups([order("WO-1", "Cutting"), order("WO-2", "Stitching", true), order("WO-3", "Stitching", true), order("WO-4", "Cutting")])
	assert.deepEqual(groups.map((group) => [group.process, group.isAffected, group.orders.map((entry) => entry.name)]), [
		["Stitching", true, ["WO-2", "WO-3"]],
		["Cutting", false, ["WO-1", "WO-4"]],
	])
	assert.deepEqual(workOrderGroups([]), [])
})

test("work order section uses hover cards, DD-MM-YYYY dates and the empty state", () => {
	const source = readFileSync(new URL("../src/departments/merch/ipd/approval/IpdApprovalWorkOrders.vue", import.meta.url), "utf8")
	assert.match(source, /No submitted Work Orders/)
	assert.match(source, /formatDisplayDate\(active\.wo_date\)/)
	assert.match(source, /<Popover/)
	assert.doesNotMatch(source, /\stitle=/)
})
