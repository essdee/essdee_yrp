"""T&A Update page API: load, preview and save actual dates on one T&A."""

import copy

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime

from essdee_yrp.time_and_action.create import LOT, TIME_AND_ACTION, get_time_and_action
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
	"auto_actual_date",
)
LOG_FIELDS = ("revised_on", "revision_no", "action", "planned_date", "from_date", "to_date", "user", "reason")


@frappe.whitelist()
def find_time_and_action(against: str, against_id: str) -> str | None:
	"""The T&A to update; a Frozen one (converted to Lot T&As) is left out."""
	name = get_time_and_action(against, against_id)
	if name and frappe.db.get_value(TIME_AND_ACTION, name, "status") == "Frozen":
		return None
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
	return {**serialize(doc), **get_delivery_change(before.end_date, doc.end_date)}


@frappe.whitelist()
def update_actual_dates(time_and_action: str, changes: list | str, modified: str) -> None:
	doc = get_doc_for_update(time_and_action, modified)
	apply_changes(doc, changes)
	frappe.flags.in_time_and_action_update = True
	try:
		doc.save()
	finally:
		frappe.flags.in_time_and_action_update = False


def get_delivery_change(before, after) -> dict:
	"""Expected delivery (last action's date) before and after; days moved in working days, later = positive."""
	return {
		"delivery_date_before": getdate(before),
		"delivery_date_after": getdate(after),
		"delivery_days_moved": get_working_day_diff(after, before, get_company_holidays()),
	}


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
		row.auto_actual_date = 0


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
		"can_complete": can_complete(doc),
		"can_reopen": doc.status == "Completed" and "System Manager" in frappe.get_roles(),
		"can_edit_steps": doc.status == "In Progress" and has_step_editor_role(settings),
		"can_split": can_split(doc),
		"can_edit_suppliers": doc.status == "In Progress" and bool(doc.has_permission("write")),
	}


def can_split(doc) -> bool:
	"""Split T&A copies an In Progress Lot T&A to other Lots; same write permission as Update."""
	return doc.status == "In Progress" and doc.against == LOT and bool(doc.has_permission("write"))


def can_complete(doc) -> bool:
	return doc.status == "In Progress" and not get_pending_actions(doc) and doc.has_permission("write")


def can_revise(doc, settings) -> bool:
	role = settings.revised_date_approver_role
	return bool(
		doc.status == "In Progress"
		and role
		and role in frappe.get_roles()
		and doc.revised < cint(settings.revising_days_limit)
	)


def has_step_editor_role(settings=None) -> bool:
	"""Update Action (add/remove steps) is for the T&A Step Editor Role or the T & A Admin Role."""
	settings = settings or frappe.get_single("SD YRP T and A Settings")
	roles = {settings.step_editor_role, settings.t_and_a_admin_role} - {None, ""}
	return bool(roles & set(frappe.get_roles()))


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
	doc.revised = cint(doc.revised) + 1
	revised_on = now_datetime()
	for row in doc.details:
		doc.append(
			"time_and_action_revised_dates",
			{
				"revised_on": revised_on,
				"revision_no": doc.revised,
				"action": row.action,
				"planned_date": row.planned_start_date,
				"from_date": row.date,
				"to_date": row.rescheduled_date,
				"user": frappe.session.user,
				"reason": reason,
			},
		)
		row.date = row.rescheduled_date
	doc.flags.revising_dates = True
	doc.save()


def validate_revision_log(doc) -> None:
	"""Revision History rows are never edited or removed; only Revise Dates (or a T&A copy) appends them."""
	before = doc.get_doc_before_save()
	old_rows = [get_log_values(row) for row in (before.time_and_action_revised_dates if before else [])]
	new_rows = [get_log_values(row) for row in doc.time_and_action_revised_dates]
	kept = new_rows[: len(old_rows)] == old_rows
	appended = len(new_rows) > len(old_rows)
	if not kept or (appended and not (doc.flags.revising_dates or doc.flags.copying)):
		frappe.throw(_("Revision History rows can be added only by Revise Dates and cannot be changed."))


def get_log_values(row) -> tuple:
	return tuple(str(row.get(field) or "") for field in LOG_FIELDS)


@frappe.whitelist()
def revert_time_and_action(time_and_action: str) -> None:
	"""Delete a T&A, actual dates included. T&A Admin only."""
	if not is_time_and_action_admin(frappe.get_single("SD YRP T and A Settings")):
		frappe.throw(_("Only the T&A Admin role can revert a Time and Action."), frappe.PermissionError)
	frappe.delete_doc(TIME_AND_ACTION, time_and_action)


@frappe.whitelist()
def complete_time_and_action(time_and_action: str) -> None:
	"""Mark a T&A Completed once every action has an actual date; it is locked after."""
	doc = frappe.get_doc(TIME_AND_ACTION, time_and_action)
	doc.check_permission("write")
	if doc.status != "In Progress":
		frappe.throw(_("Time and Action {0} is {1}.").format(time_and_action, doc.status))
	pending = get_pending_actions(doc)
	if pending:
		frappe.throw(_("Enter actual dates for all actions first. Pending: {0}").format(", ".join(pending)))
	set_status(doc, "Completed")


@frappe.whitelist()
def reopen_time_and_action(time_and_action: str) -> None:
	"""Set a Completed T&A back to In Progress, keeping its dates. System Manager only."""
	frappe.only_for("System Manager")
	doc = frappe.get_doc(TIME_AND_ACTION, time_and_action)
	doc.check_permission("write")
	if doc.status != "Completed":
		frappe.throw(_("Time and Action {0} is not Completed.").format(time_and_action))
	set_status(doc, "In Progress")


def get_pending_actions(doc) -> list[str]:
	return [row.action for row in doc.details if not row.actual_date]


def set_status(doc, status: str) -> None:
	doc.status = status
	doc.flags.changing_status = True
	doc.save()
