"""Split T&A: copy an In Progress Lot T&A to other Lots; the source and each copy continue on their own."""

import frappe
from frappe import _

from essdee_yrp.time_and_action.copy import copy_time_and_action, parse_lots
from essdee_yrp.time_and_action.create import LOT, PRODUCTION_ORDER, TIME_AND_ACTION, validate_can_create
from essdee_yrp.time_and_action.rules import ActualDateState

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
def split_time_and_action(
	time_and_action: str, lots: list | str, skipped_actions: list | str | None = None
) -> list[str]:
	"""Copy a Lot T&A to each Lot, actual dates and reasons included except for `skipped_actions`; all lots or none."""
	lots = parse_lots(lots)
	skipped_actions = frappe.parse_json(skipped_actions or "[]")
	source = get_split_source(time_and_action)
	source.check_permission("write")
	validate_split_lots(lots)
	validate_skipped_actions(source, skipped_actions)
	created = [copy_time_and_action(source, LOT, lot, skipped_actions) for lot in lots]
	log_split(source, created, lots, skipped_actions)
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


def validate_skipped_actions(source, skipped_actions: list[str]) -> None:
	"""Skipped actions belong to the source; a dated dependent of a skipped action is skipped too."""
	state = ActualDateState(source)
	for action in skipped_actions:
		if action not in state.actual:
			frappe.throw(_("{0} is not an action of Time and Action {1}.").format(action, source.name))
		kept = [name for name in state.get_dated_successors(action) if name not in skipped_actions]
		if kept:
			frappe.throw(
				_("{0} depends on {1}. Leave out its actual date too.").format(", ".join(kept), action)
			)


def log_split(source, created: list[str], lots: list[str], skipped_actions: list[str]) -> None:
	pairs = ", ".join(f"{name} ({lot})" for name, lot in zip(created, lots, strict=True))
	source.add_comment("Info", _("Split T&A to {0}. This T&A continues.").format(pairs))
	note = _("Split from Lot {0} Time and Action {1}.").format(source.against_id, source.name)
	if skipped_actions:
		note += " " + _("Actual dates not copied: {0}.").format(", ".join(skipped_actions))
	for name in created:
		frappe.get_doc(TIME_AND_ACTION, name).add_comment("Info", note)
