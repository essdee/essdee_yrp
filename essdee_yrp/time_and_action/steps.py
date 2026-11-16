"""Add and remove actions on an In Progress T&A (Update Action); one batch, validated together."""

import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from essdee_yrp.time_and_action.create import TIME_AND_ACTION, get_work_station
from essdee_yrp.time_and_action.derived import apply_schedule
from essdee_yrp.time_and_action.rules import format_date
from essdee_yrp.time_and_action.update import get_delivery_change, has_step_editor_role, serialize


@frappe.whitelist()
def preview_update_actions(
	time_and_action: str, add: list | str | None = None, remove: list | str | None = None
) -> dict:
	"""Apply the adds and removes to an unsaved copy and return the rows and the delivery impact."""
	doc = get_doc_for_step_edit(time_and_action)
	before_end = doc.end_date
	apply_action_changes(doc, add, remove)
	return {**serialize(doc), **get_delivery_change(before_end, doc.end_date)}


@frappe.whitelist()
def update_actions(
	time_and_action: str, add: list | str | None = None, remove: list | str | None = None
) -> None:
	"""Remove `remove` actions, then add `add` items in order, log each change and save once."""
	doc = get_doc_for_step_edit(time_and_action)
	before_end = doc.end_date
	messages = apply_action_changes(doc, add, remove)
	doc.save()
	delivery = _("Expected delivery {0} → {1}.").format(format_date(before_end), format_date(doc.end_date))
	doc.add_comment("Info", "<br>".join([*messages, delivery]))


def get_doc_for_step_edit(name: str):
	doc = frappe.get_doc(TIME_AND_ACTION, name)
	doc.check_permission("write")
	if doc.status != "In Progress":
		frappe.throw(_("Time and Action {0} is {1} and cannot be changed.").format(name, doc.status))
	if not has_step_editor_role():
		frappe.throw(_("You are not allowed to add or remove actions."), frappe.PermissionError)
	return doc


def apply_action_changes(doc, add, remove) -> list[str]:
	"""Change `doc` in memory and recalculate; returns one timeline line per change."""
	add, remove = frappe.parse_json(add) or [], frappe.parse_json(remove) or []
	if not (add or remove):
		frappe.throw(_("Add or remove at least one action."))
	messages = [remove_action(doc, action) for action in remove]
	messages += [add_action(doc, frappe._dict(item)) for item in add]
	apply_schedule(doc)
	return messages


def remove_action(doc, action: str) -> str:
	"""Drop an undated step; its dependents lose that dependency (requirement 32)."""
	row = get_step(doc, action)
	if row.actual_date:
		frappe.throw(_("{0} has an actual date and cannot be removed.").format(frappe.bold(action)))
	if len(doc.details) == 1:
		frappe.throw(_("A Time and Action needs at least one action."))
	before = get_step_snapshot(doc, row)
	doc.details = [item for item in doc.details if item.action != action]
	doc.dependent_details = [
		item for item in doc.dependent_details if action not in (item.action, item.dependent_action)
	]
	renumber(doc)
	log_change(doc, "Remove Step", action, before=before)
	return _("Removed {0}.").format(action)


def add_action(doc, item) -> str:
	"""Insert a new step after `after_action` with its dependencies; its baseline is its computed date."""
	position = validate_new_action(doc, item)
	values = {
		"action": item.action,
		"department": frappe.db.get_value("SD YRP Action", item.action, "department"),
		"lead_time": cint(item.lead_time),
		"work_station": get_work_station(item.action, item.work_station),
	}
	row = doc.append("details", values)
	doc.details.remove(row)
	doc.details.insert(position, row)
	for dependency in item.depends_on or []:
		doc.append("dependent_details", {"action": item.action, "dependent_action": dependency})
	for successor in item.required_by or []:
		doc.append("dependent_details", {"action": successor, "dependent_action": item.action})
	renumber(doc)
	apply_schedule(doc)
	row.date = row.planned_start_date = row.rescheduled_date
	log_change(doc, "Add Step", item.action, after=get_step_snapshot(doc, row))
	return get_add_message(item)


def validate_new_action(doc, item) -> int:
	"""Return the insert index; refuse unknown, duplicate, out-of-order or dated links."""
	if not (item.action and frappe.db.exists("SD YRP Action", item.action)):
		frappe.throw(_("Select an existing Action."))
	index = {row.action: row_index for row_index, row in enumerate(doc.details)}
	if item.action in index:
		frappe.throw(_("{0} is already on this Time and Action.").format(frappe.bold(item.action)))
	if cint(item.lead_time) < 1:
		frappe.throw(_("Lead Time of {0} must be at least 1.").format(frappe.bold(item.action)))
	position = get_insert_position(doc, item.after_action, index)
	for dependency in item.depends_on or []:
		if index.get(dependency, position) >= position:
			frappe.throw(
				_("{0} can depend only on actions above it, not {1}.").format(item.action, dependency)
			)
	for successor in item.required_by or []:
		validate_required_by(doc, item.action, successor, index, position)
	return position


def get_insert_position(doc, after_action, index) -> int:
	"""Index after `after_action` (or the top); never before the last dated action."""
	if after_action and after_action not in index:
		frappe.throw(_("{0} is not part of this Time and Action.").format(after_action))
	position = index[after_action] + 1 if after_action else 0
	dated = [row_index for row_index, row in enumerate(doc.details) if row.actual_date]
	if dated and position <= dated[-1]:
		frappe.throw(
			_("New actions can only be added after the last completed action ({0}).").format(
				doc.details[dated[-1]].action
			)
		)
	return position


def validate_required_by(doc, action, successor, index, position) -> None:
	if successor not in index:
		frappe.throw(_("{0} is not part of this Time and Action.").format(successor))
	if doc.details[index[successor]].actual_date:
		frappe.throw(
			_("{0} already has an actual date, so it cannot wait for {1}.").format(successor, action)
		)
	if index[successor] < position:
		frappe.throw(_("{0} must finish before {1}, so {1} must be below it.").format(action, successor))


def get_step(doc, action: str):
	row = next((row for row in doc.details if row.action == action), None)
	if not row:
		frappe.throw(_("{0} is not part of this Time and Action.").format(action))
	return row


def get_step_snapshot(doc, row) -> dict:
	rows = [item.action for item in doc.details]
	position = rows.index(row.action)
	return {
		"action": row.action,
		"lead_time": cint(row.lead_time),
		"after_action": rows[position - 1] if position else None,
		"depends_on": [item.dependent_action for item in doc.dependent_details if item.action == row.action],
		"required_by": [item.action for item in doc.dependent_details if item.dependent_action == row.action],
		"work_station": row.work_station,
		"expected_date": str(row.rescheduled_date or ""),
	}


def renumber(doc) -> None:
	for table in (doc.details, doc.dependent_details):
		for row_index, row in enumerate(table, start=1):
			row.idx = row_index
	for row in doc.details:
		row.index2 = row.idx


def log_change(doc, change_type: str, action: str, before=None, after=None) -> None:
	doc.append(
		"step_changes",
		{
			"change_type": change_type,
			"action": action,
			"before": json.dumps(before) if before else None,
			"after": json.dumps(after) if after else None,
			"user": frappe.session.user,
			"changed_on": now_datetime(),
		},
	)


def get_add_message(item) -> str:
	days = cint(item.lead_time)
	message = _("Added {0} ({1} {2})").format(item.action, days, _("day") if days == 1 else _("days"))
	if item.depends_on:
		message += " " + _("after {0}").format(", ".join(item.depends_on))
	if item.required_by:
		message += "; " + _("before {0}").format(", ".join(item.required_by))
	return message + "."
