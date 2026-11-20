import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { merchPurchaseLauncherItems } from "../src/departments/merch-purchase/merchPurchaseViews.js"
import { applyApprovalResult, grammageCellText, grammageDifference, grammageFilterArgs, GRAMMAGE_COLUMNS, GRAMMAGE_FILTERS } from "../src/departments/merch/laysheet-grammage/laysheetGrammageApproval.js"
import { MERCH_ROUTES, merchLauncherItems, visibleMerchLauncherItems } from "../src/departments/merch/merchViews.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"
import { getDepartmentEntries } from "../src/departments/search/departmentCards.js"
import { dedupeEntries, searchResults } from "../src/departments/search/departmentSearch.js"
import { isWorkspaceInLayout } from "../src/router/departmentLock.js"
import { getListDoctype } from "../src/router/listPermission.js"
import { lockedDepartment } from "./helpers/layout.js"

const KEY = "laysheet_grammage_approvals"
const PATH = "/merch/laysheet-grammage-approvals"
const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const department = (key) => departments.find((item) => item.key === key)

test("Merch and Merch & Purchase show one LaySheet Grammage Approval card, gated on LaySheet read", () => {
	const card = merchLauncherItems().find((item) => item.key === KEY)
	assert.deepEqual([card.label, card.to], ["LaySheet Grammage Approval", PATH])
	assert.deepEqual(merchPurchaseLauncherItems().filter((item) => item.key === KEY).map((item) => item.to), [PATH])
	assert.deepEqual(visibleMerchLauncherItems({ [KEY]: { can_read: false } }), [])
	assert.deepEqual(visibleMerchLauncherItems({ [KEY]: { can_read: true } }).map((item) => item.key), [KEY])
	assert.deepEqual(getWorkspacePaths(department("merch"))[KEY], [PATH])
	assert.deepEqual(getWorkspacePaths(department("merch-purchase"))[KEY], [PATH])
	for (const key of ["merch-pd", "quality", "accounts"]) assert.equal(getWorkspacePaths(department(key))[KEY], undefined, key)
	assert.equal(getListDoctype(PATH), "SD YRP Cutting LaySheet")
	assert.equal(MERCH_ROUTES.laysheetGrammageApprovals, "merch-laysheet-grammage-approvals")
	assert.match(source("../src/router/index.js"), /path: "\/merch\/laysheet-grammage-approvals", name: MERCH_ROUTES.laysheetGrammageApprovals/)
})

test("a Merch or Merch & Purchase layout listing the card opens it", () => {
	for (const experienceKey of ["merch", "merch-purchase"]) {
		assert.ok(isWorkspaceInLayout({ to: PATH }, lockedDepartment(experienceKey, [KEY])), experienceKey)
	}
})

test("department search lists the card once", async () => {
	const read = { can_read: true }
	const payload = { merch: { sections: { [KEY]: read }, reports: {} }, merch_purchase: { sections: { [KEY]: read } } }
	const all = dedupeEntries(await getDepartmentEntries(payload, { boot: { user: { name: "Administrator" } }, lock: null }))
	const found = searchResults(all, "grammage")
	assert.deepEqual(found.map((result) => [result.label, result.to]), [["LaySheet Grammage Approval", PATH]])
})

test("the list shows the requested columns and link filters", () => {
	assert.deepEqual(GRAMMAGE_COLUMNS.map((column) => column.label), ["Lot", "Cutting Plan", "Work Order", "Lay No", "LaySheet Date", "Item", "REQD Weight", "Actual Weight"])
	assert.ok(!GRAMMAGE_COLUMNS.some((column) => column.field === "name"), "the LaySheet ID is not a column")
	const row = { posting_date: "2026-11-05", lay_no: 3, item_name: "Tee", required_pcs_weight: 0.248, piece_weight: 0.2622 }
	const text = Object.fromEntries(GRAMMAGE_COLUMNS.map((column) => [column.label, grammageCellText(row, column)]))
	assert.deepEqual([text["LaySheet Date"], text["Lay No"], text.Item, text["REQD Weight"], text["Actual Weight"], text.Lot], ["05-11-2026", "3", "Tee", "0.248", "0.262", "—"])
	assert.deepEqual(GRAMMAGE_FILTERS.map((filter) => [filter.key, filter.doctype]), [["lot", "SD YRP Lot"], ["item", "Item"], ["cutting_plan", "SD YRP Cutting Plan"], ["work_order", "YRP Work Order"]])
	assert.deepEqual(grammageFilterArgs({ lot: "LOT-1", item: "", cutting_plan: null, work_order: "WO-1" }), { lot: "LOT-1", work_order: "WO-1" })
})

test("approved LaySheets leave the list; failures are reported per LaySheet", () => {
	const rows = [{ name: "CLS-1" }, { name: "CLS-2" }, { name: "CLS-3" }]
	const allDone = applyApprovalResult(rows, { approved: ["CLS-1", "CLS-3"], failed: [] })
	assert.deepEqual(allDone.rows.map((row) => row.name), ["CLS-2"])
	assert.equal(allDone.outcome, null)
	assert.equal(allDone.notice, "2 documents approved.")
	const partial = applyApprovalResult(rows, { approved: ["CLS-1"], failed: [{ name: "CLS-2", error: "This Cutting LaySheet is not pending approval" }] })
	assert.deepEqual(partial.rows.map((row) => row.name), ["CLS-2", "CLS-3"])
	assert.equal(partial.outcome.title, "Approve partially completed")
	assert.equal(partial.outcome.summary, "1 document approved; 1 document failed.")
	assert.deepEqual(partial.outcome.failed, [{ name: "CLS-2", error: "This Cutting LaySheet is not pending approval" }])
	const none = applyApprovalResult(rows, { approved: [], failed: [{ name: "CLS-1", error: "x" }] })
	assert.equal(none.outcome.title, "Approve failed")
	assert.equal(none.notice, "")
})

test("the page shows Approve only when the server allows it and approves through the bulk endpoint", () => {
	const page = source("../src/departments/merch/laysheet-grammage/LaySheetGrammageApprovals.vue")
	assert.match(page, /<Column v-if="canApprove" selection-mode="multiple"/)
	assert.match(page, /<Button v-if="canApprove" label="Approve"/)
	assert.match(page, /canApprove\.value = Boolean\(result\?\.can_approve\)/)
	assert.match(page, /:header="detail \? `LaySheet \$\{detail\.name\}`/, "the popup title names the LaySheet")
	assert.match(page, /<template v-for="column in GRAMMAGE_COLUMNS"/, "the popup uses the list labels")
	assert.match(source("../src/api/merch.js"), /essdee_yrp\.merch\.laysheet_grammage_approval/)
})

test("phone cards show the signed grammage difference and keep select and Approve reachable", () => {
	assert.deepEqual(grammageDifference({ required_pcs_weight: 0.229, piece_weight: 0.24 }), { text: "+0.011", tone: "over" })
	assert.deepEqual(grammageDifference({ required_pcs_weight: 0.278, piece_weight: 0.264 }), { text: "−0.014", tone: "under" })
	assert.deepEqual(grammageDifference({ required_pcs_weight: 0.1, piece_weight: 0.1 }), { text: "0", tone: "equal" })
	const page = source("../src/departments/merch/laysheet-grammage/LaySheetGrammageApprovals.vue")
	assert.match(page, /<Checkbox v-if="canApprove" v-model="selectedRows" :value="row"/)
	assert.match(page, /class="grammage-card__approve"[^>]*@click="approve\(\[row\]\)"/)
	assert.match(page, /grammage-approval__filters:not\(\.is-open\) \{ display: none; \}/, "phone filters fold behind the Filters toggle")
	assert.match(page, /\.grammage-approval \{ display: grid; grid-template-columns: minmax\(0, 1fr\)/, "the wide table cannot widen the page")
})
