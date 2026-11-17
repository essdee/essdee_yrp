import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const read = (path) => readFileSync(new URL(`../../essdee_yrp/${path}`, import.meta.url), "utf8")
const actionMeta = JSON.parse(read("essdee_yrp/doctype/sd_yrp_action/sd_yrp_action.json"))
const field = (fieldname) => actionMeta.fields.find((df) => df.fieldname === fieldname)

test("action master step picker is a plain SD YRP Action link so Frappe offers Create a new SD YRP Action", () => {
	const source = read("public/js/ActionMaster/ActionDetail.vue")
	assert.match(source, /get_input_field\("\.cur-action", "Link", "action", "SD YRP Action", "SD YRP Action", true, get_action_data\)/)
	assert.doesNotMatch(source, /only_select/)
	assert.match(source, /frappe\.db\.get_value\("SD YRP Action", val, \["department", "lead_time"\]\)/)
})

test("SD YRP Action quick entry asks for name, department, lead time, process and planning flags", () => {
	assert.equal(actionMeta.quick_entry, 1)
	assert.equal(actionMeta.autoname, "prompt")
	assert.equal(field("department").reqd, 1)
	assert.equal(field("lead_time").reqd, 1)
	const quickEntryFields = actionMeta.fields.filter((df) => df.reqd || df.allow_in_quick_entry).map((df) => df.fieldname)
	assert.deepEqual(quickEntryFields, ["department", "lead_time", "default", "capacity_planning", "default_order", "process_name"])
	assert.ok(!actionMeta.fields.some((df) => df.fieldtype === "Table" && df.reqd))
})
