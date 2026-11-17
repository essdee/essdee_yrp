"""Split T&A: copy an In Progress Lot T&A to other Lots; the source and each copy continue on their own."""

import frappe
from frappe import _

from essdee_yrp.time_and_action.copy import copy_time_and_action, parse_lots
from essdee_yrp.time_and_action.create import LOT, PRODUCTION_ORDER, TIME_AND_ACTION, validate_can_create

SPLIT_LOT_LIMIT = 50


@frappe.whitelist()
def get_split_lots(time_and_action: str, txt: str | None = None) -> list[dict]:
	"""Lots that can receive a split: no T&A of their own and no Production Order with a T&A."""
	get_split_source(time_and_action)
	planned = frappe.get_all(TIME_AND_ACTION, filters={"against": LOT}, pluck="against_id")
	orders = frappe.get_all(TIME_AND_ACTION, filters={"against": PRODUCTION_ORDER}, pluck="against_id")
	filters = [[LOT, "docstatus", "<", 2]]
	if planned:
		filters.append([LOT, "name", "not in", planned])
	if orders:
		filters.append([LOT, "production_order", "not in", orders])
	search = f"%{txt.strip()}%" if txt and txt.strip() else None
	return frappe.get_list(
		LOT,
		filters=filters,
		or_filters=[[LOT, "name", "like", search], [LOT, "item", "like", search]] if search else None,
		fields=["name", "item", "total_order_quantity as qty"],
		order_by="creation desc",
		limit_page_length=SPLIT_LOT_LIMIT,
	)


@frappe.whitelist()
def split_time_and_action(time_and_action: str, lots: list | str) -> list[str]:
	"""Copy a Lot T&A, actual dates and reasons included, to each Lot; all lots or none."""
	lots = parse_lots(lots)
	source = get_split_source(time_and_action)
	source.check_permission("write")
	validate_split_lots(lots)
	created = [copy_time_and_action(source, LOT, lot) for lot in lots]
	log_split(source, created, lots)
	return created


def get_split_source(time_and_action: str):
	source = frappe.get_doc(TIME_AND_ACTION, time_and_action)
	source.check_permission("read")
	if source.against != LOT:
		frappe.throw(
			_(
				"Split T&A works only on a Lot's Time and Action. Use Convert to Lot T&A on a Production Order."
			)
		)
	if source.status != "In Progress":
		frappe.throw(
			_("Time and Action {0} is {1}. Only an In Progress one can be split.").format(
				source.name, source.status
			)
		)
	return source


def validate_split_lots(lots: list[str]) -> None:
	if len(set(lots)) != len(lots):
		frappe.throw(_("Each Lot can be selected only once."))
	for lot in lots:
		docstatus = frappe.db.get_value(LOT, lot, "docstatus")
		if docstatus is None:
			frappe.throw(_("Lot {0} does not exist.").format(lot))
		if docstatus == 2:
			frappe.throw(_("Lot {0} is cancelled.").format(lot))
		validate_can_create(LOT, lot)


def log_split(source, created: list[str], lots: list[str]) -> None:
	pairs = ", ".join(f"{name} ({lot})" for name, lot in zip(created, lots, strict=True))
	source.add_comment("Info", _("Split T&A to {0}. This T&A continues.").format(pairs))
	for name in created:
		frappe.get_doc(TIME_AND_ACTION, name).add_comment(
			"Info", _("Split from Lot {0} Time and Action {1}.").format(source.against_id, source.name)
		)
