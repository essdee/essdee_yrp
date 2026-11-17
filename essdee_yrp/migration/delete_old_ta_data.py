import frappe

TA_DOCTYPES = (
	"SD YRP Time and Action",
	"SD YRP Time and Action Detail",
	"SD YRP Time and Action Dependent Detail",
	"SD YRP Time and Action Revised Date",
	"SD YRP Time and Action Work Station Detail",
	"SD YRP Lot Time and Action Detail",
	"SD YRP Work Station Action",
)
KEPT_DOCTYPES = (
	"SD YRP Action",
	"SD YRP Action Master",
	"SD YRP Action Master Detail",
	"SD YRP Action Master Dependent Detail",
)
LOG_FIELDS = {"Version": "ref_doctype", "Comment": "reference_doctype", "Activity Log": "reference_doctype"}


def execute():
	"""Delete old T&A transaction data; keep Action, Action Master and T&A settings. Archive the data first."""
	before = get_counts()
	for doctype, field in get_link_fields():
		frappe.db.sql(f"update `tab{doctype}` set `{field}` = NULL where `{field}` is not null")
	for doctype, field in LOG_FIELDS.items():
		frappe.db.delete(doctype, {field: ("in", TA_DOCTYPES)})
	for doctype in TA_DOCTYPES:
		frappe.db.delete(doctype)
	frappe.db.commit()
	after = get_counts()
	for label, count in before.items():
		print(f"{label}: {count} -> {after[label]}")


def get_counts():
	counts = {doctype: frappe.db.count(doctype) for doctype in TA_DOCTYPES + KEPT_DOCTYPES}
	for doctype, field in LOG_FIELDS.items():
		counts[f"{doctype} (T&A)"] = frappe.db.count(doctype, {field: ("in", TA_DOCTYPES)})
	for doctype, field in get_link_fields():
		counts[f"{doctype}.{field}"] = frappe.db.count(doctype, {field: ("is", "set")})
	return counts


def get_link_fields():
	filters = {"fieldtype": "Link", "options": "SD YRP Time and Action"}
	standard = frappe.get_all("DocField", filters=filters, fields=["parent as doctype", "fieldname"])
	custom = frappe.get_all("Custom Field", filters=filters, fields=["dt as doctype", "fieldname"])
	return sorted(
		{(row.doctype, row.fieldname) for row in standard + custom if row.doctype not in TA_DOCTYPES}
	)
