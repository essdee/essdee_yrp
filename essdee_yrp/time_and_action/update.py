"""T&A Update page API: load, preview and save actual dates on one T&A."""

import copy

import frappe
from frappe import _
from frappe.utils import cint, getdate

from essdee_yrp.time_and_action.create import TIME_AND_ACTION, get_time_and_action
from essdee_yrp.time_and_action.derived import apply_schedule
from essdee_yrp.time_and_action.holidays import get_company_holidays
from essdee_yrp.time_and_action.rules import ActualDateState, validate_actual_dates
from essdee_yrp.time_and_action.schedule import get_performance, get_working_day_diff

ROW_FIELDS = (
	"action",
	"department",
	"lead_time",
	"work_station",
	"planned_start_date",
	"date",
	"rescheduled_date",
	"actual_date",
	"reason",
	"date_diff",
	"performance",
	"actual_delay",
)


@frappe.whitelist()
def find_time_and_action(against: str, against_id: str) -> str | None:
	name = get_time_and_action(against, against_id)
	if name:
		frappe.get_doc(TIME_AND_ACTION, name).check_permission("read")
	return name


@frappe.whitelist()
def get_update_data(time_and_action: str) -> dict:
	doc = frappe.get_doc(TIME_AND_ACTION, time_and_action)
	doc.check_permission("read")
	return serialize(doc)


@frappe.whitelist()
def preview_actual_dates(time_and_action: str, changes: list | str, modified: str) -> dict:
	"""Apply `changes` to an unsaved copy, run the rules and the engine, return the result."""
	doc = get_doc_for_update(time_and_action, modified)
	before = copy.deepcopy(doc)
	apply_changes(doc, changes)
	frappe.flags.in_time_and_action_update = True
	try:
		validate_actual_dates(doc, before, require_reason=False)
	finally:
		frappe.flags.in_time_and_action_update = False
	apply_schedule(doc)
	return serialize(doc)


@frappe.whitelist()
def update_actual_dates(time_and_action: str, changes: list | str, modified: str) -> None:
	doc = get_doc_for_update(time_and_action, modified)
	apply_changes(doc, changes)
	frappe.flags.in_time_and_action_update = True
	try:
		doc.save()
	finally:
		frappe.flags.in_time_and_action_update = False


def get_doc_for_update(name: str, modified: str):
	doc = frappe.get_doc(TIME_AND_ACTION, name)
	doc.check_permission("write")
	if str(doc.modified) != str(modified):
		frappe.throw(
			_("Time and Action {0} was changed by someone else. Refresh and try again.").format(name)
		)
	return doc


def apply_changes(doc, changes) -> None:
	changes = frappe.parse_json(changes) or []
	rows = {row.action: row for row in doc.details}
	for change in changes:
		row = rows.get(change.get("action")) if isinstance(change, dict) else None
		if not row:
			frappe.throw(_("Action {0} is not part of this Time and Action.").format(change))
		row.actual_date = getdate(change["actual_date"]) if change.get("actual_date") else None
		row.reason = (change.get("reason") or "").strip() or None


def serialize(doc) -> dict:
	holidays = get_company_holidays()
	state = ActualDateState(doc)
	last = doc.details[-1]
	return {
		**{field: doc.get(field) for field in ("name", "against", "against_id", "item", "master", "qty")},
		**{field: doc.get(field) for field in ("sizes", "start_date", "status", "delay", "end_date")},
		"rescheduled_delay": doc.rescheduled_delay,
		"revised": doc.revised,
		"modified": str(doc.modified),
		"performance": get_performance(cint(doc.delay)),
		"end_date_delay": getdate(doc.end_date) > getdate(last.date),
		"rows": [serialize_row(row, state, holidays) for row in doc.details],
		"revisions": get_revisions(doc),
		**get_user_context(doc),
	}


def serialize_row(row, state: ActualDateState, holidays) -> dict:
	value = {field: row.get(field) for field in ROW_FIELDS}
	value["depends_on"] = {name: state.actual.get(name) for name in state.dependencies.get(row.action, [])}
	value["can_enter"] = state.can_enter(row.action)
	value["can_remove"] = state.can_remove(row.action)
	value["cumulative_delay"] = (
		get_working_day_diff(row.date, row.actual_date, holidays) if row.actual_date else 0
	)
	return value


def get_revisions(doc) -> dict[str, list]:
	revisions = {}
	for row in doc.time_and_action_revised_dates:
		revisions.setdefault(row.action, []).append(row.from_date)
	return revisions


def get_user_context(doc) -> dict:
	settings = frappe.get_single("SD YRP T and A Settings")
	departments = frappe.get_all("YRP Department User", filters={"user": frappe.session.user}, pluck="parent")
	return {
		"departments": departments,
		"is_administrator": frappe.session.user == "Administrator",
		"can_revise": can_revise(doc, settings),
		"can_revert": is_time_and_action_admin(settings),
	}


def can_revise(doc, settings) -> bool:
	role = settings.revised_date_approver_role
	return bool(role and role in frappe.get_roles() and doc.revised < cint(settings.revising_days_limit))


def is_time_and_action_admin(settings) -> bool:
	return bool(settings.t_and_a_admin_role and settings.t_and_a_admin_role in frappe.get_roles())


@frappe.whitelist()
def revise_dates(time_and_action: str, reason: str) -> None:
	"""Freeze the expected dates as the new baseline."""
	if not (reason or "").strip():
		frappe.throw(_("A revision reason is required."))
	doc = frappe.get_doc(TIME_AND_ACTION, time_and_action)
	doc.check_permission("write")
	if not can_revise(doc, frappe.get_single("SD YRP T and A Settings")):
		frappe.throw(_("You are not allowed to revise this Time and Action."), frappe.PermissionError)
	for row in doc.details:
		doc.append(
			"time_and_action_revised_dates",
			{
				"action": row.action,
				"from_date": row.date,
				"to_date": row.rescheduled_date,
				"user": frappe.session.user,
				"reason": reason,
			},
		)
		row.date = row.rescheduled_date
	doc.revised = cint(doc.revised) + 1
	doc.save()


@frappe.whitelist()
def complete_time_and_action(time_and_action: str) -> None:
	doc = frappe.get_doc(TIME_AND_ACTION, time_and_action)
	doc.check_permission("write")
	pending = [row.action for row in doc.details if not row.actual_date]
	if pending:
		frappe.throw(_("Enter actual dates for all actions first. Pending: {0}").format(", ".join(pending)))
	doc.status = "Completed"
	doc.save()


@frappe.whitelist()
def revert_time_and_action(time_and_action: str) -> None:
	"""Delete a T&A, actual dates included. T&A Admin only."""
	if not is_time_and_action_admin(frappe.get_single("SD YRP T and A Settings")):
		frappe.throw(_("Only the T&A Admin role can revert a Time and Action."), frappe.PermissionError)
	frappe.delete_doc(TIME_AND_ACTION, time_and_action)
