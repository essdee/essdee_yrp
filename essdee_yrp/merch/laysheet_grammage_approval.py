import frappe
from frappe import _

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet import (
	approve_grammage,
	can_approve_grammage,
)

DOCTYPE = "SD YRP Cutting LaySheet"
PENDING_STATUS = "Approval Pending"
FIELDS = [
	"name",
	"lot",
	"cutting_plan",
	"lay_no",
	"posting_date",
	"item",
	"required_pcs_weight",
	"piece_weight",
]


@frappe.whitelist()
def get_pending_laysheets(lot=None, item=None, cutting_plan=None, work_order=None) -> dict:
	"""Cutting LaySheets awaiting grammage approval, with whether the user may approve them."""
	frappe.has_permission(DOCTYPE, "read", throw=True)
	filters = {"status": PENDING_STATUS, "docstatus": 0}
	for fieldname, value in (("lot", lot), ("item", item), ("cutting_plan", cutting_plan)):
		if value:
			filters[fieldname] = value
	if work_order:
		plans = frappe.get_all("SD YRP Cutting Plan", filters={"work_order": work_order}, pluck="name")
		if cutting_plan and cutting_plan not in plans:
			plans = []
		filters["cutting_plan"] = ["in", plans or [""]]
	rows = frappe.get_list(DOCTYPE, filters=filters, fields=FIELDS, order_by="modified desc")
	return {"rows": add_plan_details(rows), "can_approve": bool(can_approve_grammage())}


def add_plan_details(rows):
	"""Adds each row's Work Order (from its Cutting Plan) and Item name."""
	work_orders = get_field_by_name("SD YRP Cutting Plan", {row.cutting_plan for row in rows}, "work_order")
	item_names = get_field_by_name("Item", {row.item for row in rows}, "item_name")
	for row in rows:
		row.work_order = work_orders.get(row.cutting_plan)
		row.item_name = item_names.get(row.item) or row.item
	return rows


def get_field_by_name(doctype, names, fieldname):
	names = [name for name in names if name]
	if not names:
		return {}
	return dict(
		frappe.get_all(doctype, filters={"name": ["in", names]}, fields=["name", fieldname], as_list=True)
	)


@frappe.whitelist(methods=["POST"])
def approve_laysheets(laysheets) -> dict:
	"""Approve grammage on each LaySheet in its own savepoint; failures are reported per LaySheet."""
	names = frappe.parse_json(laysheets) if isinstance(laysheets, str) else list(laysheets or [])
	if not names:
		frappe.throw(_("Select at least one Cutting LaySheet to approve."))
	if not can_approve_grammage():
		frappe.throw(_("You do not have the required role to approve grammage"), frappe.PermissionError)
	previous = frappe.flags.mute_messages
	frappe.flags.mute_messages = True
	try:
		return approve_each(names)
	finally:
		frappe.flags.mute_messages = previous


def approve_each(names):
	approved, failed = [], []
	for index, name in enumerate(names, start=1):
		savepoint = f"laysheet_grammage_approval_{index}"
		frappe.db.savepoint(savepoint)
		try:
			approve_grammage(name)
			approved.append(name)
		except Exception as error:
			frappe.db.rollback(save_point=savepoint)
			failed.append({"name": name, "error": frappe.utils.strip_html(str(error)) or _("Failed")})
	return {"approved": approved, "failed": failed}
