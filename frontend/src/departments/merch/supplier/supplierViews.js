export const SUPPLIER_DOCTYPE = "Supplier"
export const SUPPLIERS_PATH = "/merch/suppliers"
export const SUPPLIER_LIST_COLUMNS = ["supplier_name", "supplier_group", "supplier_type", "gstin", "disabled"]
export const ADDRESS_CONTACT_GROUP = "address_contact"

/** Page groups in order, taken from the Desk Supplier tabs ("main" is the untitled first tab) and sections. */
const SUPPLIER_GROUPS = [
	{ key: "details", label: "Details", tabs: ["main"] },
	{ key: ADDRESS_CONTACT_GROUP, label: "Address & Contact", tabs: ["contact_and_address_tab"], existingOnly: true },
	{ key: "accounting", label: "Accounting", tabs: ["accounting_tab"] },
	{ key: "tax", label: "Tax", tabs: ["tax_tab"] },
	{ key: "tax_identification", label: "Tax Identification", sections: ["taxation_section"] },
	{ key: "settings", label: "Settings", tabs: ["settings_tab"] },
]

/** Section holding the title field leads Details as its unlabelled main section, like the Desk form's first section. */
function detailsFirst(sections, titleField) {
	const index = sections.findIndex((section) => section.columns.flat().some((field) => field.fieldname === titleField))
	if (index < 0) return sections
	return [{ ...sections[index], label: "" }, ...sections.filter((_, position) => position !== index)]
}

/** FormView tabs regrouped into the Supplier page order; other Desk tabs follow; Address & Contact shows once saved. */
export function supplierGroups(tabs, meta, { existing = false } = {}) {
	const claimedSections = new Set(SUPPLIER_GROUPS.flatMap((group) => group.sections || []))
	const claimedTabs = new Set(SUPPLIER_GROUPS.flatMap((group) => group.tabs || []))
	const allSections = tabs.flatMap((tab) => tab.sections)
	const groups = SUPPLIER_GROUPS.filter((group) => existing || !group.existingOnly).map((group) => {
		const fromTabs = tabs.filter((tab) => group.tabs?.includes(tab.key)).flatMap((tab) => tab.sections).filter((section) => !claimedSections.has(section.key))
		const named = allSections.filter((section) => group.sections?.includes(section.key)).map((section) => ({ ...section, label: section.label === group.label ? "" : section.label }))
		const sections = [...fromTabs, ...named]
		return { key: group.key, label: group.label, keep: Boolean(group.existingOnly), sections: group.key === "details" ? detailsFirst(sections, meta?.title_field) : sections }
	})
	const rest = tabs.filter((tab) => !claimedTabs.has(tab.key)).map((tab) => ({ ...tab, sections: tab.sections.filter((section) => !claimedSections.has(section.key)) }))
	return withTablesLast([...groups, ...rest])
}

/** Departments, YRP Account Mappings and Supplier Users close the page inside More Info. */
const LAST_TABLES = ["deparments", "account_mappings", "supplier_users"]
const LAST_TAB = "more_info_tab"

function withTablesLast(groups) {
	const moved = groups.flatMap((group) => group.sections.flatMap((section) => section.tables)).filter((table) => LAST_TABLES.includes(table.fieldname))
	if (!moved.length) return groups
	const isEmpty = (section) => !section.tables.length && !section.columns.some((column) => column.length)
	const trimmed = groups.map((group) => ({
		...group,
		sections: group.sections.map((section) => ({ ...section, tables: section.tables.filter((table) => !LAST_TABLES.includes(table.fieldname)) })).filter((section) => !isEmpty(section)),
	}))
	const last = trimmed.find((group) => group.key === LAST_TAB) || { key: LAST_TAB, label: "More Info", sections: [] }
	const tablesSection = { key: "supplier-last-tables", label: "", columns: [[]], tables: moved }
	return [...trimmed.filter((group) => group !== last), { ...last, sections: [...last.sections, tablesSection] }]
}

/** Address and Contact cards linked to a Supplier through their Dynamic Links, as Desk lists them. */
export const LINKED_RECORDS = {
	Address: {
		label: "Addresses",
		singular: "Address",
		fields: ["name", "address_title", "address_type", "address_line1", "address_line2", "city", "state", "pincode", "country", "gstin", "phone", "email_id", "is_primary_address", "is_shipping_address", "disabled"],
		orderBy: "is_primary_address desc, modified desc",
		title: (row) => row.address_title || row.name,
		badges: (row) => [row.address_type, row.is_primary_address && "Primary", row.is_shipping_address && "Shipping", row.disabled && "Disabled"].filter(Boolean),
		lines: (row) => [
			[row.address_line1, row.address_line2].filter(Boolean).join(", "),
			[row.city, row.state, row.pincode].filter(Boolean).join(", "),
			row.country,
			row.gstin && `GSTIN: ${row.gstin}`,
			[row.phone, row.email_id].filter(Boolean).join(" · "),
		].filter(Boolean),
	},
	Contact: {
		label: "Contacts",
		singular: "Contact",
		fields: ["name", "first_name", "last_name", "designation", "email_id", "mobile_no", "phone", "is_primary_contact", "status"],
		orderBy: "is_primary_contact desc, modified desc",
		title: (row) => [row.first_name, row.last_name].filter(Boolean).join(" ") || row.name,
		badges: (row) => [row.is_primary_contact && "Primary"].filter(Boolean),
		lines: (row) => [row.designation, row.email_id, [row.mobile_no, row.phone].filter(Boolean).join(" · ")].filter(Boolean),
	},
}

export function linkedRecordFilters(supplier) {
	return [["Dynamic Link", "link_doctype", "=", SUPPLIER_DOCTYPE], ["Dynamic Link", "link_name", "=", supplier]]
}

export function newLinkedRecordValues(supplier) {
	return { links: [{ link_doctype: SUPPLIER_DOCTYPE, link_name: supplier }] }
}
