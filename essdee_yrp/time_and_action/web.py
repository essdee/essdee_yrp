"""/web Planning API for Time and Action: open T&A list and the Lot page context."""

import frappe

from essdee_yrp.time_and_action.create import LOT, TIME_AND_ACTION, get_time_and_action

DETAIL = "SD YRP Time and Action Detail"

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
	"""In Progress T&As (not Completed or Frozen), newest first, with progress and next action; `lot` keeps only that Lot's T&A."""
	filters = {"status": "In Progress"}
	if lot:
		filters.update({"against": LOT, "against_id": lot})
	if item:
		filters["item"] = item
	rows = frappe.get_list(TIME_AND_ACTION, filters=filters, fields=list(LIST_FIELDS), order_by="creation desc")
	add_progress(rows)
	return rows


def add_progress(rows: list[dict]) -> None:
	"""Set `dated`, `total`, `next_action` and `next_action_date` (its Rescheduled Date) on each row."""
	if not rows:
		return
	details = frappe.get_all(
		DETAIL,
		filters={"parent": ["in", [row.name for row in rows]], "parenttype": TIME_AND_ACTION},
		fields=["parent", "action", "rescheduled_date", "actual_date"],
		order_by="parent, idx",
	)
	by_parent = {}
	for detail in details:
		by_parent.setdefault(detail.parent, []).append(detail)
	for row in rows:
		actions = by_parent.get(row.name, [])
		pending = [detail for detail in actions if not detail.actual_date]
		row.update(
			{
				"dated": len(actions) - len(pending),
				"total": len(actions),
				"next_action": pending[0].action if pending else None,
				"next_action_date": pending[0].rescheduled_date if pending else None,
			}
		)


@frappe.whitelist()
def get_lot_time_and_action(lot: str) -> dict:
	"""The Lot's T&A (if any) and the Create T&A dialog facts; like Desk, creating needs an assigned person."""
	doc = frappe.get_doc(LOT, lot)
	doc.check_permission("read")
	if not frappe.has_permission(TIME_AND_ACTION, "read"):
		return {"can_read": False}
	name = get_time_and_action(LOT, lot)
	if name:
		frappe.get_doc(TIME_AND_ACTION, name).check_permission("read")
	may_create = not name and frappe.has_permission(TIME_AND_ACTION, "create")
	needs_assigned_person = bool(may_create and not doc.assigned_person)
	return {
		"can_read": True,
		"time_and_action": name,
		"can_create": bool(may_create and doc.assigned_person),
		"create_blocked_reason": "no_assigned_person" if needs_assigned_person else None,
		"item": doc.item,
		"qty": doc.total_order_quantity,
	}
