"""Actual dates set and cleared by production (requirement 34), on Lot T&As only."""

import frappe
from frappe.utils import flt, getdate

from essdee_yrp.time_and_action.create import LOT, TIME_AND_ACTION, get_time_and_action
from essdee_yrp.time_and_action.rules import LOCKED_STATUSES, ActualDateState

AUTO_REASON = "NA"
LOG_TITLE = "T&A auto actual date skipped"


def get_actual_date_percentage() -> float:
	"""The T&A Actual Date % from SD YRP MRP Settings; 0 means the feature is off."""
	return flt(frappe.db.get_single_value("SD YRP MRP Settings", "ta_actual_date_percentage"))


def get_process_names(process_name: str | None) -> list[str]:
	"""The process plus its sub-processes when it is a group."""
	if not process_name:
		return []
	process = frappe.get_cached_doc("YRP Process", process_name)
	sub_processes = [row.process_name for row in process.get("process_details") or [] if row.process_name]
	names = [process_name, *(sub_processes if process.get("is_group") else [])]
	return list(dict.fromkeys(names))


def get_open_lot_time_and_action(lot: str):
	"""The Lot's T&A for automation, or None when it has none or it is Completed or Frozen."""
	name = get_time_and_action(LOT, lot)
	if not name or frappe.db.get_value(TIME_AND_ACTION, name, "status") in LOCKED_STATUSES:
		return None
	doc = frappe.get_doc(TIME_AND_ACTION, name)
	doc.flags.auto_actual_date = True
	return doc


def get_process_rows(doc, process_names: list[str]) -> list:
	"""Detail rows whose SD YRP Action maps to one of `process_names`."""
	if not process_names:
		return []
	actions = frappe.get_all(
		"SD YRP Action",
		filters={"name": ["in", [row.action for row in doc.details]], "process_name": ["in", process_names]},
		pluck="name",
	)
	return [row for row in doc.details if row.action in actions]


def set_auto_actual_date(lot: str, process_names: list[str], date) -> list[str]:
	"""Date the undated actions of `process_names`; rows failing the T&A rules are skipped and logged."""
	doc = get_open_lot_time_and_action(lot)
	if not doc or not date:
		return []
	date = getdate(date)
	state = ActualDateState(doc)
	updated = []
	for row in get_process_rows(doc, process_names):
		if not row.actual_date and try_set_row(state, row, date):
			updated.append(row.action)
	return updated if updated and save_quietly(doc, updated) else []


def try_set_row(state: ActualDateState, row, date) -> bool:
	reason = row.reason
	row.actual_date = date
	if date > getdate(row.rescheduled_date):
		row.reason = AUTO_REASON
	error = get_rule_error(lambda: state.validate_new_actual(row))
	if error:
		row.actual_date, row.reason = None, reason
		log_skip(row, error)
		return False
	row.auto_actual_date = 1
	state.actual[row.action] = date
	return True


def clear_auto_actual_date(lot: str, process_names: list[str]) -> list[str]:
	"""Clear dates the automation set; a row whose successor is already dated is skipped and logged."""
	doc = get_open_lot_time_and_action(lot)
	if not doc:
		return []
	state = ActualDateState(doc)
	cleared = []
	for row in reversed(get_process_rows(doc, process_names)):
		if not (row.actual_date and row.auto_actual_date):
			continue
		error = get_rule_error(lambda row=row: state.validate_no_dated_successor(row.action))
		if error:
			log_skip(row, error)
			continue
		row.actual_date = None
		row.auto_actual_date = 0
		row.reason = None if row.reason == AUTO_REASON else row.reason
		state.actual[row.action] = None
		cleared.append(row.action)
	return cleared if cleared and save_quietly(doc, cleared) else []


def get_rule_error(check) -> str | None:
	"""Run a rule that throws; return its message without leaving it for the user."""
	message_count = len(frappe.local.message_log)
	try:
		check()
	except frappe.ValidationError as error:
		return str(error)
	finally:
		del frappe.local.message_log[message_count:]
	return None


def save_quietly(doc, actions: list[str]) -> bool:
	"""Save through the normal T&A validation; on failure roll back to a savepoint and log."""
	previous = frappe.flags.in_time_and_action_update
	message_count = len(frappe.local.message_log)
	frappe.db.savepoint("time_and_action_auto_date")
	frappe.flags.in_time_and_action_update = True
	try:
		doc.save(ignore_permissions=True)
		return True
	except Exception:
		frappe.db.rollback(save_point="time_and_action_auto_date")
		del frappe.local.message_log[message_count:]
		frappe.log_error(LOG_TITLE, f"{doc.name}: saving {', '.join(actions)} failed")
		return False
	finally:
		frappe.flags.in_time_and_action_update = previous


def log_skip(row, error: str) -> None:
	frappe.log_error(LOG_TITLE, f"{row.parent} / {row.action}: {error}")
