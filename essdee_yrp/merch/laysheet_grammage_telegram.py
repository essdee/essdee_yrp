import frappe
from frappe import _
from frappe.utils import flt

DOCTYPE = "SD YRP Cutting LaySheet"
PENDING_STATUS = "Approval Pending"
APPROVED_STATUS = "Bundles Generated"
APPROVE_ACTION = "Approve"
MESSAGE_TEMPLATE = """\
LAYSHEET GRAMMAGE APPROVAL
───────────────────────
Lot: {{ doc.lot or "-" }}
Cutting Plan: {{ doc.cutting_plan or "-" }}
Lay No: {{ doc.lay_no or "-" }}
Item: {{ doc.item or "-" }}

Required Weight: {{ laysheet.required_weight }}
Actual Weight: {{ laysheet.actual_weight }}
Difference: {{ laysheet.difference }} ({{ laysheet.difference_percent }})
Tolerance: ±{{ laysheet.tolerance }}"""
ROUTE_VALUES = {
	"reference_doctype": DOCTYPE,
	"process_type": "Field State",
	"trigger_field": "status",
	"trigger_value": PENDING_STATUS,
	"approve_action": APPROVE_ACTION,
	"reject_action": "",
	"target_field": "status",
	"approve_value": APPROVED_STATUS,
	"reject_value": "",
	"approve_roles": "",
	"reject_roles": "",
}


def apply_route_values(route):
	"""Force the fixed LaySheet route values; grammage roles in SD YRP MRP Settings decide who approves."""
	route.update(ROUTE_VALUES)
	if not route.get("message_template"):
		route.update({"message_template": MESSAGE_TEMPLATE})


def get_message_context(doc):
	from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet import (
		get_laysheet_piece_weight_tolerance,
	)

	required = flt(doc.get("required_pcs_weight"))
	actual = flt(doc.get("piece_weight"))
	difference = actual - required
	return {
		"laysheet": frappe._dict(
			required_weight=f"{required:.3f}",
			actual_weight=f"{actual:.3f}",
			difference=f"{difference:+.3f}",
			difference_percent=f"{difference / required * 100:+.2f}%" if required else "-",
			tolerance=f"{flt(get_laysheet_piece_weight_tolerance(doc)):.3f}",
		)
	}


def approve_from_telegram(doc, route, action_key, action_name, target_field, target_value):
	"""Telegram Approve runs approve_grammage as the mapped user, so its role check applies."""
	if (action_key, target_field, target_value) != ("a", "status", APPROVED_STATUS):
		frappe.throw(_("Invalid Cutting LaySheet Telegram approval action configuration."))
	from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet import approve_grammage

	approve_grammage(doc.name)
	updated_doc = frappe.get_doc(DOCTYPE, doc.name)
	updated_doc.add_comment(
		"Comment", _("Telegram action {0} performed by {1}.").format(action_name, frappe.session.user)
	)
	return updated_doc


def get_outside_approval(doc):
	"""Approver when the LaySheet was approved outside Telegram, else None."""
	if doc.get("status") == APPROVED_STATUS and doc.get("approved_by"):
		return doc.approved_by
	return None
