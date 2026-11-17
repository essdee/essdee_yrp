"""T&A against a Production Order: Desk and /web context, Convert to Lot T&A, and the Lot link rule."""

import frappe
from frappe import _

from essdee_yrp.time_and_action.copy import copy_time_and_action, parse_lots
from essdee_yrp.time_and_action.create import (
	LOT,
	PRODUCTION_ORDER,
	TIME_AND_ACTION,
	get_linked_lots,
	get_production_order_qty,
	get_time_and_action,
)
from essdee_yrp.time_and_action.update import set_status

CONVERTIBLE_STATUSES = ("In Progress", "Frozen")


@frappe.whitelist()
def get_production_order_time_and_action(production_order: str) -> dict:
	"""The order's T&A (Frozen included), what the user can do with it, and the Lot T&As converted from it."""
	order = frappe.get_doc(PRODUCTION_ORDER, production_order)
	order.check_permission("read")
	if not frappe.has_permission(TIME_AND_ACTION, "read"):
		return {"can_read": False}
	name = get_time_and_action(PRODUCTION_ORDER, production_order)
	status = frappe.db.get_value(TIME_AND_ACTION, name, "status") if name else None
	can_write = frappe.has_permission(TIME_AND_ACTION, "create")
	may_create = bool(not name and order.docstatus != 2 and can_write)
	has_lots = may_create and bool(get_linked_lots(order.name))
	return {
		"can_read": True,
		"time_and_action": name,
		"status": status,
		"can_create": may_create and not has_lots,
		"create_blocked_reason": "linked_lots" if has_lots else None,
		"can_convert": bool(status in CONVERTIBLE_STATUSES and can_write),
		"copies": get_copies(name) if name else [],
		"item": order.item,
		"qty": get_production_order_qty(order),
	}


def get_planned_lots(production_order: str) -> list[str]:
	lots = frappe.get_all(LOT, filters={"production_order": production_order}, pluck="name")
	if not lots:
		return []
	return frappe.get_all(
		TIME_AND_ACTION, filters={"against": LOT, "against_id": ["in", lots]}, pluck="against_id"
	)


def get_copies(time_and_action: str) -> list[dict]:
	return frappe.get_all(
		TIME_AND_ACTION,
		filters={"copied_from": time_and_action},
		fields=["name", "against_id as lot", "status"],
		order_by="creation asc",
	)


@frappe.whitelist()
def get_convertible_lots(time_and_action: str) -> list[dict]:
	"""Lots linked to the T&A's Production Order that have no T&A yet."""
	source = get_convert_source(time_and_action)
	planned = set(get_planned_lots(source.against_id))
	lots = frappe.get_list(
		LOT,
		filters={"production_order": source.against_id},
		fields=["name", "item", "total_order_quantity as qty"],
		order_by="name asc",
	)
	return [lot for lot in lots if lot.name not in planned]


@frappe.whitelist()
def convert_to_lot_time_and_action(time_and_action: str, lots: list | str) -> list[str]:
	"""Copy a Production Order T&A to each Lot, then freeze it; all lots or none."""
	lots = parse_lots(lots)
	source = get_convert_source(time_and_action)
	source.check_permission("write")
	validate_convert_lots(source, lots)
	created = [copy_time_and_action(source, LOT, lot) for lot in lots]
	if source.status != "Frozen":
		set_status(source, "Frozen")
	log_conversion(source, created, lots)
	return created


def get_convert_source(time_and_action: str):
	source = frappe.get_doc(TIME_AND_ACTION, time_and_action)
	source.check_permission("read")
	if source.against != PRODUCTION_ORDER:
		frappe.throw(_("Convert to Lot T&A works only on a Production Order's Time and Action."))
	if source.status not in CONVERTIBLE_STATUSES:
		frappe.throw(_("Time and Action {0} is {1}.").format(source.name, source.status))
	return source


def validate_convert_lots(source, lots: list[str]) -> None:
	if len(set(lots)) != len(lots):
		frappe.throw(_("Each Lot can be selected only once."))
	for lot in lots:
		if frappe.db.get_value(LOT, lot, "production_order") != source.against_id:
			frappe.throw(_("Lot {0} is not linked to Production Order {1}.").format(lot, source.against_id))
		existing = get_time_and_action(LOT, lot)
		if existing:
			frappe.throw(_("Lot {0} already has Time and Action {1}.").format(lot, existing))


def log_conversion(source, created: list[str], lots: list[str]) -> None:
	pairs = ", ".join(f"{name} ({lot})" for name, lot in zip(created, lots, strict=True))
	source.add_comment("Info", _("Converted to Lot T&A: {0}. This T&A is frozen.").format(pairs))
	for name in created:
		frappe.get_doc(TIME_AND_ACTION, name).add_comment(
			"Info",
			_("Converted from Production Order {0} Time and Action {1}.").format(
				source.against_id, source.name
			),
		)


def validate_lot_link(lot) -> None:
	"""A Lot with its own T&A cannot be linked to a Production Order that has a T&A."""
	if lot.is_new() or not lot.production_order or not lot.has_value_changed("production_order"):
		return
	own = get_time_and_action(LOT, lot.name)
	order_time_and_action = own and get_time_and_action(PRODUCTION_ORDER, lot.production_order)
	if order_time_and_action:
		frappe.throw(
			_(
				"Lot {0} has Time and Action {1} and Production Order {2} has Time and Action {3}. Revert one before linking."
			).format(lot.name, own, lot.production_order, order_time_and_action)
		)
