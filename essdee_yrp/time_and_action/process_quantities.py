"""Colour × size cut, delivered and received quantities of a T&A action's process, for the Update hover pop-up."""

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.planning.reports.production_quantities import matrix_identity, variant_attributes
from essdee_yrp.time_and_action.auto_date import get_process_names
from essdee_yrp.time_and_action.create import LOT, TIME_AND_ACTION
from essdee_yrp.time_and_action.work_order_dates import (
	get_calculated_rows,
	get_cut_rows,
	get_item_quantities,
)

QUANTITIES = ("cut", "delivered", "received")


@frappe.whitelist()
def get_action_process_quantities(time_and_action: str, action: str) -> dict:
	"""Lot T&A only: per colour, set part and size of the action's process, cut qty and Work Order delivered/received."""
	doc = frappe.get_doc(TIME_AND_ACTION, time_and_action)
	doc.check_permission("read")
	if action not in {row.action for row in doc.details}:
		frappe.throw(
			_("{0} is not an action of Time and Action {1}.").format(action, time_and_action),
			frappe.DoesNotExistError,
		)
	process_name = frappe.db.get_value("SD YRP Action", action, "process_name")
	result = {"action": action, "process_name": process_name, "lot": None, "is_cutting": False}
	if not process_name or doc.against != LOT:
		return {**result, **build_quantities([], lambda row: ("", "", ""), [])}
	lot = doc.against_id
	frappe.has_permission(LOT, "read", lot, throw=True)
	production_detail = frappe.db.get_value(LOT, lot, "production_detail")
	ipd = frappe.get_cached_doc("YRP Item Production Detail", production_detail) if production_detail else {}
	process_names = get_process_names(process_name)
	items = get_item_quantities(get_cut_rows(lot), get_calculated_rows(lot, process_names)).values()
	attributes = variant_attributes({row["item_variant"] for row in items})
	return {
		**result,
		"lot": lot,
		"is_cutting": bool(ipd and ipd.cutting_process in process_names),
		**build_quantities(items, lambda row: matrix_identity(row, attributes, ipd), get_sizes(ipd)),
	}


def get_sizes(ipd) -> list[str]:
	from yrp.yrp.doctype.yrp_item_production_detail.yrp_item_production_detail import (
		get_ipd_primary_values,
	)

	return list(get_ipd_primary_values(ipd.name) or []) if ipd else []


def build_quantities(items, identity, sizes: list[str]) -> dict:
	"""Rows per (colour, part, size) in IPD size order, skipping all-zero rows, plus totals; % is of cut."""
	rows = {}
	for item in items:
		if not any(flt(item[key]) for key in QUANTITIES):
			continue
		colour, part, size = identity(item)
		row = rows.setdefault(
			(colour, part, size),
			{"colour": colour, "part": part, "size": size, **dict.fromkeys(QUANTITIES, 0.0)},
		)
		for key in QUANTITIES:
			row[key] += flt(item[key])
	sizes = [*sizes, *sorted({size for _colour, _part, size in rows} - set(sizes))]
	ordered = sorted(rows.values(), key=lambda row: (row["colour"], row["part"], sizes.index(row["size"])))
	totals = {key: sum(row[key] for row in ordered) for key in QUANTITIES}
	return {
		"sizes": sizes,
		"rows": [with_percent(row) for row in ordered],
		"totals": with_percent(totals),
	}


def with_percent(row: dict) -> dict:
	cut = flt(row["cut"])
	return {
		**row,
		"delivered_percent": flt(row["delivered"] * 100 / cut, 1) if cut else None,
		"received_percent": flt(row["received"] * 100 / cut, 1) if cut else None,
	}
