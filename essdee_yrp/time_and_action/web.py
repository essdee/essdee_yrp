"""/web Planning API for Time and Action: open T&A list and the Lot page context."""

import frappe

from essdee_yrp.time_and_action.create import LOT, TIME_AND_ACTION, get_time_and_action

LIST_FIELDS = (
	"name",
	"against",
	"against_id",
	"item",
	"master",
	"qty",
	"start_date",
	"end_date",
	"delay",
	"rescheduled_delay",
	"status",
)


@frappe.whitelist()
def get_open_time_and_actions(lot: str | None = None, item: str | None = None) -> list[dict]:
	"""T&As that are not Completed, newest first; `lot` keeps only that Lot's T&A."""
	filters = {"status": ["!=", "Completed"]}
	if lot:
		filters.update({"against": LOT, "against_id": lot})
	if item:
		filters["item"] = item
	return frappe.get_list(TIME_AND_ACTION, filters=filters, fields=list(LIST_FIELDS), order_by="creation desc")


@frappe.whitelist()
def get_lot_time_and_action(lot: str) -> dict:
	"""The Lot's T&A (if any) and the Create T&A dialog facts; like Desk, creating needs an assigned person."""
	doc = frappe.get_doc(LOT, lot)
	doc.check_permission("read")
	name = get_time_and_action(LOT, lot)
	if name:
		frappe.get_doc(TIME_AND_ACTION, name).check_permission("read")
	can_create = not name and bool(doc.assigned_person) and frappe.has_permission(TIME_AND_ACTION, "create")
	return {
		"time_and_action": name,
		"can_create": bool(can_create),
		"item": doc.item,
		"qty": doc.total_order_quantity,
	}
