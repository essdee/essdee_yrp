import assert from "node:assert/strict"
import test from "node:test"

const { getWorkspacePaths, departments } = await import("../src/departments/registry.js")
const { accountsLauncherItems, accountsReportTabs } = await import("../src/departments/accounts/accountsViews.js")

test("Accounts shows the Merch Lot and Process Cost and PD Lotwise Item Profit cards before Reports", () => {
	assert.deepEqual(accountsLauncherItems().map((item) => [item.key, item.to]), [
		["debits", "/accounts/debits"],
		["purchase_invoices", "/accounts/purchase-invoices"],
		["bill_tracking", "/accounts/bill-tracking"],
		["lots", "/accounts/lots"],
		["process_costs", "/merch/process-costs"],
		["lotwise_item_profits", "/pd/lotwise-item-profits"],
		["reports", "/accounts/reports"],
	])
})

test("the Accounts layout opens only the combined Lot, Process Cost and Lotwise Item Profit pages", () => {
	const paths = getWorkspacePaths(departments.find((item) => item.key === "accounts"))

	assert.deepEqual(paths.lots, ["/accounts/lots", "/merch/lots"])
	assert.deepEqual(paths.process_costs, ["/merch/process-costs"])
	assert.deepEqual(paths.lotwise_item_profits, ["/pd/lotwise-item-profits"])
	assert.equal(paths.item_production_details, undefined)
})

test("Accounts Reports lists Lot Cut Quantity with the Cutting Plan link flag", () => {
	const tabs = accountsReportTabs({ lot_cut_quantity: { can_read: true, can_read_cutting_plan: true } })

	assert.deepEqual(tabs.map((tab) => [tab.value, tab.componentProps]), [["lot-cut-quantity", { canReadCuttingPlan: true }]])
	assert.deepEqual(accountsReportTabs({ lot_cut_quantity: { can_read: false } }), [])
})
