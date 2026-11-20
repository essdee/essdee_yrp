import frappe
from frappe import _

from essdee_yrp.purchase import lot_editor
from essdee_yrp.web_common import assert_expected_modified

DOCTYPE = "SD YRP Lot"
UNLINK_ROLES = {"Merch Manager", "System Manager"}
DOWNSTREAM_DOCUMENTS = (
	("YRP Work Order", {"docstatus": ["<", 2]}),
	("SD YRP Cutting Plan", {"docstatus": ["<", 2]}),
	("YRP Stock Ledger Entry", {"is_cancelled": 0}),
)


def can_unlink_ppo(doc, user=None):
	"""Assigned person, Merch Manager or System Manager."""
	user = user or frappe.session.user
	return bool(doc.assigned_person and doc.assigned_person == user) or bool(
		UNLINK_ROLES & set(frappe.get_roles(user))
	)


def get_downstream_document(lot):
	for doctype, filters in DOWNSTREAM_DOCUMENTS:
		if name := frappe.db.get_value(doctype, {"lot": lot, **filters}, "name"):
			return doctype, name
	return None


def get_unlink_ppo_block(doc):
	if not doc.production_order:
		return _("No Production Order is linked.")
	if doc.get("is_transferred"):
		return _("The Lot was transferred.")
	if doc.has_time_and_action:
		return _("Time & Action exists. Revert it before unlinking the Production Order.")
	if downstream := get_downstream_document(doc.name):
		return _("{0} {1} exists for this Lot. Cancel it before unlinking the Production Order.").format(
			_(downstream[0]), downstream[1]
		)
	return ""


def get_unlink_ppo_capability(doc):
	visible = bool(doc.production_order) and can_unlink_ppo(doc)
	reason = get_unlink_ppo_block(doc) if visible else ""
	return {"visible": visible, "allowed": visible and not reason, "label": _("Unlink PPO"), "reason": reason}


def unlink_ppo(doc):
	"""Clear the PPO, Item, IPD and box rows; Lot.before_save drops the PPO's lotwise rows."""
	if not can_unlink_ppo(doc):
		frappe.throw(
			_("Only the assigned person or a Merch Manager can unlink the PPO."), frappe.PermissionError
		)
	if reason := get_unlink_ppo_block(doc):
		frappe.throw(reason)
	production_order = doc.production_order
	previous_ipd = doc.production_detail
	doc.update({"production_order": "", "item": "", "production_detail": ""})
	lot_editor._apply_production_detail_defaults(doc, previous_ipd)
	doc.set("items", [])
	doc.set("lot_order_details", [])
	doc.save()
	doc.add_comment("Info", _("Unlinked Production Order {0}").format(production_order))
	return production_order


@frappe.whitelist(methods=["POST"])
def unlink_lot_production_order(lot: str, expected_modified: str) -> dict:
	doc = frappe.get_doc(DOCTYPE, lot)
	doc.check_permission("write")
	assert_expected_modified(doc, expected_modified)
	return {"name": doc.name, "production_order": unlink_ppo(doc)}
