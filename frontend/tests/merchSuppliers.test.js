import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"

import { ACCOUNTS_ROUTES } from "../src/departments/accounts/accountsViews.js"
import { MERCH_PD_ROUTES } from "../src/departments/merch-pd/merchPdRoutes.js"
import { merchPurchaseLauncherItems } from "../src/departments/merch-purchase/merchPurchaseViews.js"
import { MERCH_PURCHASE_ROUTES } from "../src/departments/merch-purchase/merchPurchaseRoutes.js"
import { MERCH_ROUTES, merchLauncherItems, visibleMerchLauncherItems } from "../src/departments/merch/merchViews.js"
import { PD_ROUTES } from "../src/departments/pd/pdViews.js"
import { PLANNING_ROUTES } from "../src/departments/planning/planningViews.js"
import { PURCHASE_ROUTES } from "../src/departments/purchase/purchaseViews.js"
import { QUALITY_ROUTES } from "../src/departments/quality/qualityRoutes.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"
import { getLockedDepartment, getLockedRedirect, isWorkspaceInLayout, LAYOUT_UNAVAILABLE_PATH } from "../src/router/departmentLock.js"
import { getListDoctype, getPermissionRedirect } from "../src/router/listPermission.js"
import { webDocumentPath } from "../src/router/webDocumentRoutes.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const layouts = JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json"))
const department = (key) => departments.find((item) => item.key === key)

function lockedTo(experienceKey) {
	const workspaces = JSON.parse(layouts.find((layout) => layout.experience_key === experienceKey).config).experience_props.workspaces
	return getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: experienceKey }, config: { experience_props: { workspaces } } } })
}

function loadRouter() {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, MERCH_PD_ROUTES, MERCH_PURCHASE_ROUTES, QUALITY_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH: "/no-permission" }
	vm.runInNewContext(routerSource, context)
	return context.router
}

test("Merch and Merch & Purchase show one Supplier card before Reports, gated on Supplier read", () => {
	const keys = merchLauncherItems().map((item) => item.key)
	assert.deepEqual(keys.slice(-3), ["suppliers", "laysheet_grammage_approvals", "reports"])
	const card = merchLauncherItems().find((item) => item.key === "suppliers")
	assert.deepEqual([card.label, card.to], ["Supplier", "/merch/suppliers"])
	assert.deepEqual(merchPurchaseLauncherItems().filter((item) => item.key === "suppliers").map((item) => item.to), ["/merch/suppliers"])
	assert.deepEqual(visibleMerchLauncherItems({ suppliers: { can_read: false } }).map((item) => item.key), [])
	assert.deepEqual(visibleMerchLauncherItems({ suppliers: { can_read: true } }).map((item) => item.key), ["suppliers"])
	assert.deepEqual(getWorkspacePaths(department("merch")).suppliers, ["/merch/suppliers"])
	assert.deepEqual(getWorkspacePaths(department("merch-purchase")).suppliers, ["/merch/suppliers"])
	for (const key of ["merch-pd", "quality", "accounts"]) assert.equal(getWorkspacePaths(department(key)).suppliers, undefined, key)
})

test("Supplier list, new and record pages resolve under Merch with the Supplier read guard", () => {
	const router = loadRouter()
	const list = router.resolve("/merch/suppliers")
	const created = router.resolve("/merch/suppliers/new")
	const record = router.resolve("/merch/suppliers/SUP-0001")
	assert.deepEqual([list.name, created.name, record.name], [MERCH_ROUTES.suppliers, MERCH_ROUTES.supplierNew, MERCH_ROUTES.supplier])
	assert.equal(created.matched.at(-1).components.default, record.matched.at(-1).components.default)
	assert.equal(record.params.supplierId, "SUP-0001")
	assert.equal(getListDoctype("/merch/suppliers"), "Supplier")
	assert.equal(getPermissionRedirect(list, { user: { can_read: ["Supplier"] } }), undefined)
	assert.equal(getPermissionRedirect(list, { user: { can_read: [] } }).query.doctype, "Supplier")
})

test("Merch and Merch & Purchase layouts open Suppliers", () => {
	const router = loadRouter()
	for (const experienceKey of ["merch", "merch-purchase"]) {
		const locked = lockedTo(experienceKey)
		assert.ok(locked.workspaces.includes("suppliers"), experienceKey)
		assert.ok(isWorkspaceInLayout({ to: "/merch/suppliers" }, locked), experienceKey)
		for (const path of ["/merch/suppliers", "/merch/suppliers/new", "/merch/suppliers/SUP-1"]) {
			assert.equal(getLockedRedirect(router.resolve(path), locked), undefined, `${experienceKey} ${path}`)
		}
	}
	assert.ok(!lockedTo("merch-pd").workspaces.includes("suppliers"))
})

test("Supplier links stay inside Merch and keep their Desk fallback elsewhere", () => {
	assert.equal(webDocumentPath("Supplier", "SUP/1", "/web/merch/lots/LOT-1"), "/web/merch/suppliers/SUP%2F1")
	assert.equal(webDocumentPath("Supplier", "SUP-1", "/web/merch-purchase/lots/LOT-1"), "/web/merch/suppliers/SUP-1")
	assert.equal(webDocumentPath("Supplier", "SUP-1", "/web/fabric-store/work-orders/WO-1"), "/web/document-unavailable?doctype=Supplier&name=SUP-1")
})

const field = (fieldname) => ({ fieldname, fieldtype: "Data" })
const section = (key, label, ...fieldnames) => ({ key, label, columns: [fieldnames.map(field)], tables: [] })
const table = (fieldname) => ({ fieldname, fieldtype: "Table" })
const deskTabs = () => [
	{ key: "main", label: "", sections: [
		{ ...section("main-section", "", "uid"), tables: [table("deparments"), table("account_mappings")] },
		{ ...section("user_mapping_section", "User Mapping"), tables: [table("supplier_users")] },
		section("section_break_10", "Price List", "supplier_name", "supplier_type"),
		section("defaults_section", "Defaults", "default_currency"),
	] },
	{ key: "accounting_tab", label: "Accounting", sections: [section("internal_supplier_section", "Internal Supplier Details", "is_internal_supplier")] },
	{ key: "tax_tab", label: "Tax", sections: [section("tax_details_section", "Tax Details", "gstin", "pan"), section("taxation_section", "Tax Identification", "tax_id")] },
	{ key: "settings_tab", label: "Settings", sections: [section("settings_tab-section", "", "disabled")] },
	{ key: "portal_users_tab", label: "Portal Users", sections: [{ ...section("portal_users_tab-section", ""), tables: [table("portal_users")] }] },
	{ key: "more_info_tab", label: "More Info", sections: [section("column_break2", "More Information", "website")] },
]

test("the Supplier page groups the Desk tabs: Details, Address & Contact, Accounting, Tax, Tax Identification, Settings, then the rest", async () => {
	const { supplierGroups } = await import("../src/departments/merch/supplier/supplierViews.js")
	const groups = supplierGroups(deskTabs(), { title_field: "supplier_name" }, { existing: true })
	assert.deepEqual(groups.map((group) => group.label), ["Details", "Address & Contact", "Accounting", "Tax", "Tax Identification", "Settings", "Portal Users", "More Info"])
	assert.deepEqual(groups[0].sections.map((item) => [item.key, item.label]), [["section_break_10", ""], ["main-section", ""], ["defaults_section", "Defaults"]], "the title field's section leads Details")
	assert.deepEqual([groups[1].keep, groups[1].sections], [true, []], "Address & Contact renders the linked records even without fields")
	assert.deepEqual(groups[3].sections.map((item) => item.key), ["tax_details_section"])
	assert.deepEqual(groups[4].sections.map((item) => [item.key, item.label]), [["taxation_section", ""]])
	const moreInfo = groups.at(-1)
	assert.deepEqual(moreInfo.sections.map((item) => item.key), ["column_break2", "supplier-last-tables"])
	assert.deepEqual(moreInfo.sections.at(-1).tables.map((item) => item.fieldname), ["deparments", "account_mappings", "supplier_users"], "the three tables close the page inside More Info")
	assert.ok(groups.slice(0, -1).every((group) => group.sections.every((item) => !item.tables.some((tableField) => ["deparments", "account_mappings", "supplier_users"].includes(tableField.fieldname)))))
	assert.ok(!groups[0].sections.some((item) => item.key === "user_mapping_section"), "a section left empty by the move is dropped")
	assert.deepEqual(groups[6].sections[0].tables.map((item) => item.fieldname), ["portal_users"])
	const unsaved = supplierGroups(deskTabs(), { title_field: "supplier_name" })
	assert.ok(!unsaved.some((group) => group.key === "address_contact"), "a new Supplier has no Address & Contact yet, as in Desk")
})

test("Address & Contact lists the records linked to the Supplier and creates new ones linked to it", async () => {
	const { LINKED_RECORDS, linkedRecordFilters, newLinkedRecordValues } = await import("../src/departments/merch/supplier/supplierViews.js")
	assert.deepEqual(Object.keys(LINKED_RECORDS), ["Address", "Contact"])
	assert.deepEqual(linkedRecordFilters("SUP-1"), [["Dynamic Link", "link_doctype", "=", "Supplier"], ["Dynamic Link", "link_name", "=", "SUP-1"]])
	assert.deepEqual(newLinkedRecordValues("SUP-1"), { links: [{ link_doctype: "Supplier", link_name: "SUP-1" }] })
	const address = { name: "A-1", address_title: "Main", address_type: "Billing", address_line1: "1 Road", city: "Tiruppur", state: "Tamil Nadu", pincode: "641601", country: "India", gstin: "33ABC", is_primary_address: 1 }
	assert.deepEqual(LINKED_RECORDS.Address.badges(address), ["Billing", "Primary"])
	assert.deepEqual(LINKED_RECORDS.Address.lines(address), ["1 Road", "Tiruppur, Tamil Nadu, 641601", "India", "GSTIN: 33ABC"])
	assert.equal(LINKED_RECORDS.Contact.title({ name: "C-1", first_name: "Ravi", last_name: "K" }), "Ravi K")
})

test("the shared form hides fields of hidden Desk sections and can regroup into an even grid", () => {
	const formView = source("../src/components/common/FormView.vue")
	assert.match(formView, /groupLayout: \{ type: Function, default: null \}/)
	assert.match(formView, /uniformGrid: \{ type: Boolean, default: false \}/)
	assert.match(formView, /withoutHiddenSections\(meta\.value\?\.fields/)
	assert.match(formView, /<slot name="tab-end"/)
	const page = source("../src/departments/merch/supplier/SupplierPage.vue")
	assert.match(page, /:group-layout="groupLayout" uniform-grid/)
})
