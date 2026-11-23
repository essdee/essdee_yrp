import frappe
from frappe.utils import now, strip_html_tags

FAILED_PREFIX = "Action Failed"


@frappe.whitelist()
def get_rename_status(doctype: str, old_name: str, new_name: str, since: str | None = None) -> dict:
	"""Progress of a rename queued by `update_document_title(enqueue=1)`, as Desk queues it."""
	frappe.has_permission(doctype, "read", throw=True)
	checked_at = now()
	old_exists = frappe.db.get_value(doctype, old_name, "name") == old_name
	if not old_exists and frappe.db.exists(doctype, new_name):
		return {"status": "done", "name": new_name, "checked_at": checked_at}
	error = since and old_exists and get_failed_rename_error(doctype, old_name, since)
	if error:
		return {"status": "failed", "error": error, "checked_at": checked_at}
	return {"status": "running", "checked_at": checked_at}


def get_failed_rename_error(doctype, name, since):
	"""The error `frappe.model.document.execute_action` records as a comment when the queued rename fails."""
	content = frappe.db.get_value(
		"Comment",
		{
			"reference_doctype": doctype,
			"reference_name": name,
			"comment_type": "Comment",
			"content": ["like", FAILED_PREFIX + "%"],
			"creation": [">=", since],
		},
		"content",
		order_by="creation desc",
	)
	return content and strip_html_tags(content.removeprefix(FAILED_PREFIX)).strip()
