"""Essdee Action/Time-and-Action behavior layered onto base YRP Work Station."""

import frappe
from frappe import _
from yrp.utils import update_if_string_instance

from essdee_yrp.time_and_action.create import get_work_station


def validate_default_action_work_station(doc, method=None):
	if not doc.get("default"):
		return
	if not doc.get("action"):
		frappe.throw(_("Action is required for a default Work Station."))
	filters = {"action": doc.action, "default": 1}
	if not doc.is_new():
		filters["name"] = ["!=", doc.name]
	existing = frappe.get_all("YRP Work Station", filters=filters, pluck="name", limit=1)
	if existing:
		frappe.throw(
			_("Work Station {0} is already the default for Action {1}.").format(
				frappe.bold(existing[0]), frappe.bold(doc.action)
			)
		)


@frappe.whitelist()
def get_work_stations(time_and_action: str) -> dict:
	"""Rows of one T&A keyed by its name, the shape the Work Station editor expects."""
	doc = frappe.get_doc("SD YRP Time and Action", time_and_action)
	doc.check_permission("read")
	if doc.status != "In Progress":
		return {}
	return {doc.name: [dict(row.as_dict(), master=doc.master) for row in doc.details]}


@frappe.whitelist()
def update_t_and_a_ws(datas) -> None:
	datas = update_if_string_instance(datas)
	if not isinstance(datas, dict) or len(datas) != 1:
		frappe.throw(_("Invalid Work Station update."))
	name, rows = next(iter(datas.items()))
	doc = frappe.get_doc("SD YRP Time and Action", name)
	doc.check_permission("write")
	incoming = {row.get("action"): row.get("work_station") for row in rows or []}
	if set(incoming) != {row.action for row in doc.details}:
		frappe.throw(_("Time and Action rows changed. Refresh and try again."))
	for row in doc.details:
		row.work_station = get_work_station(row.action, incoming[row.action]) if incoming[row.action] else None
	doc.save()
