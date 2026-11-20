import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { recordActions } from "../src/departments/merch/ipd/ipdEditor.js"
import { lockSavedRows, tableGrid } from "../src/departments/merch/ipd/sections/garmentGrids.js"

const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

test("approved IPD locks saved process rows and leaves new rows editable and removable", () => {
	const grid = lockSavedRows(tableGrid([{ name: "a1", process_name: "Print" }, { process_name: "Wash" }], ["process_name"]))
	assert.deepEqual(grid.rows.map(({ key, readonly, removable }) => ({ key, readonly, removable })), [
		{ key: "a1", readonly: true, removable: false },
		{ key: "new:1", readonly: undefined, removable: undefined },
	])
	assert.deepEqual(grid.model.a1, { process_name: "Print" })
})

test("approved IPD offers the restricted edit only when the server allows it", () => {
	const allowed = { allowed: true, label: "Edit packing / combinations" }
	const keys = (capabilities) => recordActions({ approved: true, capabilities }).map((action) => action.key)
	assert.deepEqual(keys({ approved_edits: allowed, revert_approval: allowed }), ["edit", "revert_approval"])
	assert.deepEqual(keys({ approved_edits: { allowed: false }, revert_approval: allowed }), ["revert_approval"])
	assert.equal(recordActions({ approved: true, capabilities: { approved_edits: allowed } })[0].label, "Edit packing / combinations")
})

test("restricted editor opens only the process add action and embellishment panels", () => {
	const section = source("departments/merch/ipd/sections/IpdProcessesSection.vue")
	assert.match(section, /label="Add process"/)
	assert.match(section, /part === 'general' && \(!editor\.readonly \|\| editor\.approvedEdits\)" label="Add process"/)
	assert.match(section, /editor\.approvedEdits \? lockSavedRows\(grid\) : grid/)
	assert.match(section, /:model-value="embellishment\.model"\n\t+:readonly="editor\.readonly && !editor\.approvedEdits"/)
	assert.match(section, /<div v-if="!editor\.readonly" class="ipd-inline-add">/)
	const editor = source("departments/merch/ipd/useIpdEditor.js")
	assert.match(editor, /readonly: viewOnly, approvedEdits, canEdit, canEditMappings/)
	assert.match(source("components/common/EntryGrid.vue"), /:disabled="row\.removable === false"/)
	assert.match(source("components/common/EntryGrid.vue"), /props\.rows\.filter\(\(row\) => row\.removable !== false\)/)
})

test("editor is view only whenever the server denies edit, including no write permission", () => {
	const editor = source("departments/merch/ipd/useIpdEditor.js")
	assert.match(editor, /const viewOnly = computed\(\(\) => Boolean\(payload\.value\) && !capabilities\.value\.edit\?\.allowed\)/)
	const desk = readFileSync(new URL("../../essdee_yrp/public/js/item_production_detail.js", import.meta.url), "utf8")
	assert.match(desk, /return frm\.is_new\(\) \|\| frappe\.perm\.has_perm\(frm\.doctype, 0, "write", frm\.doc\)/)
	assert.match(desk, /const view_only = cloth \|\| !can_write_ipd\(frm\)/)
	const lock = readFileSync(new URL("../../essdee_yrp/public/js/ipd_mapping_lock.js", import.meta.url), "utf8")
	assert.match(lock, /__onload\?\.ipd_mapping_lock/)
	assert.match(lock, /frm\.disable_form\(\)/)
})

test("approved edits open packing and combination controls named by the server", () => {
	const editor = source("departments/merch/ipd/useIpdEditor.js")
	assert.match(editor, /const canEdit = \(fieldname\) => !viewOnly\.value \|\| approvedFields\.value\.has\(fieldname\)/)
	assert.match(editor, /capabilities\.value\.approved_edits\?\.fields/)
	const packing = source("departments/merch/ipd/sections/IpdPackingSection.vue")
	assert.match(packing, /:readonly="!editor\.canEdit\('packing_attribute_details'\)"/)
	assert.doesNotMatch(packing, /editor\.readonly/)
	assert.match(source("departments/merch/ipd/sections/IpdFields.vue"), /<dl v-if="!editable" class="ipd-facts">/)
	assert.match(source("departments/merch/ipd/sections/IpdStitchingSection.vue"), /:readonly="!editor\.canEdit\('stiching_item_detail'\) \|\| isSame"/)
	assert.match(source("departments/merch/ipd/sections/IpdCuttingSection.vue"), /:readonly="!editor\.canEdit\('cutting_items_json'\)"/)
	const desk = readFileSync(new URL("../../essdee_yrp/public/js/item_production_detail.js", import.meta.url), "utf8")
	for (const field of ["based_on_other_attribute_mapping", "packing_combo", "stiching_items_html", "dependent_attribute_details_html"]) {
		assert.match(desk, new RegExp(`"${field}"`))
	}
	assert.match(desk, /serialise_combination_widgets\(frm\)\n\t+return/)
})
