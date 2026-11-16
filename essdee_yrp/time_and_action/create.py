"""Create a Time and Action from one Action Master against a Lot or Production Order."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate

from essdee_yrp.time_and_action.holidays import get_company_holidays
from essdee_yrp.time_and_action.schedule import ScheduleRow, build_schedule

TIME_AND_ACTION = "SD YRP Time and Action"
LOT = "SD YRP Lot"
PRODUCTION_ORDER = "YRP Production Order"
AGAINST_DOCTYPES = (LOT, PRODUCTION_ORDER)


def get_master_dependencies(master) -> dict[str, list[str]]:
	dependencies = {}
	for row in master.action_master_dependent_details:
		dependencies.setdefault(row.action, []).append(row.dependent_action)
	return dependencies


def get_master_schedule(master, start_date) -> dict:
	rows = [ScheduleRow(row.action, row.lead_time) for row in master.details]
	return build_schedule(rows, get_master_dependencies(master), start_date, get_company_holidays())


def get_master_lead_time(master) -> int:
	if not master.details:
		return 0
	schedule = get_master_schedule(master, nowdate())
	return date_diff(schedule[master.details[-1].action], nowdate())


def validate_master_steps(master) -> None:
	"""Every dependency is an earlier row of the same master; actions are unique."""
	position = {}
	for row in master.details:
		if row.action in position:
			frappe.throw(_("Action {0} appears more than once.").format(frappe.bold(row.action)))
		position[row.action] = row.idx
	for row in master.action_master_dependent_details:
		_validate_dependency(row.action, row.dependent_action, position)


def _validate_dependency(action, dependency, position):
	if action == dependency:
		frappe.throw(_("Action {0} cannot depend on itself.").format(frappe.bold(action)))
	if action not in position or dependency not in position:
		frappe.throw(_("Dependency {0} → {1} must use actions of this master.").format(dependency, action))
	if position[dependency] >= position[action]:
		frappe.throw(
			_("{0} depends on {1}, so {1} must come earlier in the list.").format(
				frappe.bold(action), frappe.bold(dependency)
			)
		)


@frappe.whitelist()
def get_schedule_preview(master: str, start_date: str) -> list[dict]:
	master_doc = frappe.get_doc("SD YRP Action Master", master)
	master_doc.check_permission("read")
	schedule = get_master_schedule(master_doc, getdate(start_date))
	dependencies = get_master_dependencies(master_doc)
	return [
		{
			"action": row.action,
			"department": row.department,
			"lead_time": row.lead_time,
			"date": schedule[row.action],
			"depends_on": dependencies.get(row.action, []),
			"work_station": get_work_station(row.action),
		}
		for row in master_doc.details
	]


@frappe.whitelist()
def create_time_and_action(
	against: str, against_id: str, master: str, start_date: str, work_stations: dict | None = None
) -> str:
	frappe.has_permission(TIME_AND_ACTION, "create", throw=True)
	doc = frappe.new_doc(TIME_AND_ACTION)
	doc.update({"against": against, "against_id": against_id, "master": master, "start_date": start_date})
	doc.flags.work_stations = frappe.parse_json(work_stations) if work_stations else {}
	doc.insert()
	return doc.name


def set_rows_from_master(doc) -> None:
	"""Snapshot the master's steps, dependencies and planned dates onto `doc`."""
	master = _get_usable_master(doc.master)
	schedule = get_master_schedule(master, getdate(doc.start_date))
	work_stations = doc.flags.work_stations or {}
	for index, row in enumerate(master.details, start=1):
		day = schedule[row.action]
		doc.append(
			"details",
			{
				"action": row.action,
				"department": row.department
				or frappe.db.get_value("SD YRP Action", row.action, "department"),
				"lead_time": row.lead_time,
				"date": day,
				"planned_start_date": day,
				"rescheduled_date": day,
				"rescheduled_start_date": day,
				"index2": index,
				"work_station": get_work_station(row.action, work_stations.get(row.action)),
			},
		)
	for row in master.action_master_dependent_details:
		doc.append("dependent_details", {"action": row.action, "dependent_action": row.dependent_action})


def _get_usable_master(name):
	if not name:
		frappe.throw(_("Select an Action Master."))
	master = frappe.get_doc("SD YRP Action Master", name)
	master.check_permission("read")
	if master.disable or master.docstatus == 2:
		frappe.throw(_("Action Master {0} is disabled or cancelled.").format(frappe.bold(name)))
	if not master.details:
		frappe.throw(_("Action Master {0} has no actions.").format(frappe.bold(name)))
	return master


def get_work_station(action: str, chosen: str | None = None) -> str | None:
	if chosen:
		if frappe.db.get_value("YRP Work Station", chosen, "action") != action:
			frappe.throw(_("Work Station {0} is not configured for Action {1}.").format(chosen, action))
		return chosen
	if not frappe.db.get_value("SD YRP Action", action, "capacity_planning"):
		return None
	default = frappe.db.get_value("YRP Work Station", {"action": action, "default": 1}, "name")
	if not default:
		frappe.throw(_("There is no default Work Station for Action {0}.").format(frappe.bold(action)))
	return default


def set_against_details(doc) -> None:
	if doc.against not in AGAINST_DOCTYPES:
		frappe.throw(_("Time and Action can be created only against a Lot or a Production Order."))
	source = frappe.get_doc(doc.against, doc.against_id)
	source.check_permission("read")
	if doc.against == LOT:
		doc.item, doc.qty, ipd = source.item, flt(source.total_order_quantity), source.production_detail
	else:
		if source.docstatus == 2:
			frappe.throw(_("Production Order {0} is cancelled.").format(frappe.bold(source.name)))
		ipd = source.production_detail
		doc.item = frappe.db.get_value("YRP Item Production Detail", ipd, "item") if ipd else None
		doc.qty = sum(flt(row.quantity) for row in source.production_order_details)
	doc.sizes = get_sizes(ipd)


def get_sizes(ipd: str | None) -> str | None:
	if not ipd:
		return None
	from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import get_packing_attributes

	return (get_packing_attributes(ipd).get("sizes") or "").rstrip(",") or None


def get_time_and_action(against: str, against_id: str) -> str | None:
	"""The T&A of a Lot or Production Order, frozen ones included."""
	return frappe.db.get_value(TIME_AND_ACTION, {"against": against, "against_id": against_id}, "name")


def validate_can_create(against: str, against_id: str) -> None:
	existing = get_time_and_action(against, against_id)
	if existing:
		frappe.throw(_("{0} {1} already has Time and Action {2}.").format(_(against), against_id, existing))
	if against == LOT:
		_validate_lot_order_has_no_time_and_action(against_id)
	else:
		_validate_order_lots_have_no_time_and_action(against_id)


def _validate_lot_order_has_no_time_and_action(lot):
	order = frappe.db.get_value(LOT, lot, "production_order")
	existing = order and get_time_and_action(PRODUCTION_ORDER, order)
	if existing:
		frappe.throw(
			_(
				"Production Order {0} has Time and Action {1}. Use Convert to Lot T&A on the Production Order."
			).format(order, existing)
		)


def _validate_order_lots_have_no_time_and_action(order):
	lots = frappe.get_all(LOT, filters={"production_order": order}, pluck="name")
	planned = lots and frappe.get_all(
		TIME_AND_ACTION, filters={"against": LOT, "against_id": ["in", lots]}, pluck="against_id"
	)
	if planned:
		frappe.throw(
			_("Lots {0} of this Production Order already have Time and Action.").format(", ".join(planned))
		)
