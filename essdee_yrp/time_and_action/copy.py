"""Copy a T&A, with its rows, dates, actuals and logs, onto another Lot or Production Order."""

import frappe
from frappe import _

from essdee_yrp.time_and_action.create import TIME_AND_ACTION

HEADER_FIELDS = ("master", "start_date", "description", "revised")
TABLES = (
	"details",
	"dependent_details",
	"planned_suppliers",
	"time_and_action_revised_dates",
	"step_changes",
)


def copy_time_and_action(source, against: str, against_id: str) -> str:
	"""Insert a copy of `source` against `against_id`; the engine re-derives rescheduled dates and delays."""
	doc = frappe.new_doc(TIME_AND_ACTION)
	doc.update({field: source.get(field) for field in HEADER_FIELDS})
	doc.update({"against": against, "against_id": against_id, "copied_from": source.name})
	for table in TABLES:
		for row in source.get(table):
			doc.append(table, row.as_dict(no_default_fields=True))
	doc.flags.copying = True
	doc.insert()
	return doc.name


def parse_lots(lots: list | str | None) -> list[str]:
	"""Lots from Desk/web as a JSON list, one plain name, or a list; at least one is required."""
	lots = frappe.parse_json(lots) if isinstance(lots, str) and lots.startswith("[") else lots
	lots = [lots] if isinstance(lots, str) else list(lots or [])
	if not lots:
		frappe.throw(_("Select at least one Lot."))
	return lots
