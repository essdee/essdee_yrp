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
PROTECTED_DOCTYPES = ("SD YRP Action", "SD YRP Action Master")
LOG_TABLES = (
	("Version", "ref_doctype"),
	("Comment", "reference_doctype"),
	("File", "attached_to_doctype"),
)


def execute(dry_run=True):
	"""Delete all old T&A transaction rows; Action and Action Master stay untouched."""
	if set(TA_DOCTYPES) & set(PROTECTED_DOCTYPES):
		frappe.throw("Refusing to delete SD YRP Action or SD YRP Action Master")

	targets = [(doctype, None) for doctype in TA_DOCTYPES]
	targets += [(log, {field: ("in", TA_DOCTYPES)}) for log, field in LOG_TABLES]
	for doctype, filters in targets:
		print(f"{doctype}: {frappe.db.count(doctype, filters)}")

	if dry_run:
		print("Dry run: nothing deleted. Pass dry_run=False to delete.")
		return

	frappe.flags.in_migrate = True
	frappe.flags.mute_emails = True
	for doctype, filters in targets:
		frappe.db.delete(doctype, filters)
	frappe.db.commit()
	print("Deleted.")
