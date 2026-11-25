import frappe
from frappe.utils import get_fullname

MATCH_FIELDS = ("lot", "item", "supplier", "process_name")
SUMMARY_FIELDS = (
	"name",
	"wo_date",
	"status",
	"planned_quantity",
	"total_no_of_pieces_delivered",
	"total_no_of_pieces_received",
	"owner",
)


@frappe.whitelist()
def get_duplicate_work_orders(work_order: str) -> list[dict]:
	"""Other submitted Work Orders for the same lot, item, supplier and process (informational only)."""
	frappe.has_permission("YRP Work Order", "read", doc=work_order, throw=True)
	values = frappe.db.get_value("YRP Work Order", work_order, MATCH_FIELDS, as_dict=True)
	if not values or not all(values.values()):
		return []
	rows = frappe.get_list(
		"YRP Work Order",
		filters={**values, "docstatus": 1, "name": ("!=", work_order)},
		fields=SUMMARY_FIELDS,
		order_by="creation asc",
	)
	for row in rows:
		row["created_by"] = get_fullname(row.pop("owner"))
	return rows
