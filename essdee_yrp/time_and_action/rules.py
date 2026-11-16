"""Server rules for entering, changing and removing T&A actual dates."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, formatdate, getdate, nowdate

from essdee_yrp.time_and_action.derived import get_dependencies

LOCKED_STATUSES = ("Frozen", "Completed")


def format_date(value) -> str:
	return formatdate(value, "dd-mm-yyyy")


def validate_actual_dates(doc, before=None, require_reason=True) -> None:
	"""Check every actual date or reason that differs from `before` (default: the saved doc)."""
	before = before or doc.get_doc_before_save()
	old_rows = {row.action: row for row in (before.details if before else [])}
	changed = [row for row in doc.details if _is_changed(row, old_rows.get(row.action))]
	validate_not_locked(doc, before, old_rows, changed)
	if not changed:
		return
	if not frappe.flags.in_time_and_action_update:
		frappe.throw(_("Actual dates and reasons can be entered only from the T&A Update page."))
	state = ActualDateState(doc, require_reason)
	for row in changed:
		old_actual = _get_actual(old_rows.get(row.action))
		if old_actual and old_actual != str(row.actual_date or ""):
			state.validate_no_dated_successor(row.action)
		if row.actual_date and str(row.actual_date) != old_actual:
			state.validate_new_actual(row)


def validate_not_locked(doc, before, old_rows, changed) -> None:
	"""A Frozen or Completed T&A keeps its dates; its status changes only through Complete or Reopen."""
	if not before:
		return
	if doc.status != before.status and not doc.flags.changing_status:
		frappe.throw(_("Use Complete T&A or Reopen T&A to change the status of {0}.").format(doc.name))
	if before.status not in LOCKED_STATUSES:
		return
	if changed or any(str(row.date or "") != str(old_rows[row.action].date or "") for row in doc.details):
		frappe.throw(_("Time and Action {0} is {1} and cannot be changed.").format(doc.name, before.status))


def _get_actual(row) -> str:
	return str(row.actual_date or "") if row else ""


def _is_changed(row, old) -> bool:
	old_reason = (old.reason or "") if old else ""
	return str(row.actual_date or "") != _get_actual(old) or (row.reason or "") != old_reason


class ActualDateState:
	"""Actual dates and dependency links of one T&A as they will be saved."""

	def __init__(self, doc, require_reason=True):
		self.require_reason = require_reason
		self.actual = {
			row.action: getdate(row.actual_date) if row.actual_date else None for row in doc.details
		}
		self.dependencies = get_dependencies(doc)
		self.successors = {}
		for action, depends_on in self.dependencies.items():
			for dependency in depends_on:
				self.successors.setdefault(dependency, []).append(action)

	def can_enter(self, action) -> bool:
		return not self.actual[action] and all(self.actual.get(d) for d in self.dependencies.get(action, []))

	def can_remove(self, action) -> bool:
		return bool(self.actual[action]) and not self.get_dated_successors(action)

	def get_dated_successors(self, action) -> list[str]:
		return [name for name in self.successors.get(action, []) if self.actual.get(name)]

	def validate_no_dated_successor(self, action) -> None:
		dated = self.get_dated_successors(action)
		if dated:
			frappe.throw(
				_("Remove the actual date of {0} before changing {1}.").format(", ".join(dated), action)
			)

	def validate_new_actual(self, row) -> None:
		validate_window(row.actual_date)
		depends_on = self.dependencies.get(row.action, [])
		missing = [name for name in depends_on if not self.actual.get(name)]
		if missing:
			frappe.throw(_("Enter the actual date of {0} before {1}.").format(", ".join(missing), row.action))
		latest = max((self.actual[name] for name in depends_on), default=None)
		if latest and getdate(row.actual_date) < latest:
			frappe.throw(
				_("Actual date of {0} must be on or after {1}, the latest date of its dependencies.").format(
					row.action, format_date(latest)
				)
			)
		if (
			self.require_reason
			and getdate(row.actual_date) > getdate(row.rescheduled_date)
			and not row.reason
		):
			frappe.throw(
				_("Enter a reason: {0} is later than its expected date {1}.").format(
					row.action, format_date(row.rescheduled_date)
				)
			)


def validate_window(actual_date) -> None:
	settings = frappe.get_single("SD YRP T and A Settings")
	today = getdate(nowdate())
	earliest = getdate(add_days(today, -cint(settings.update_last_n_dates)))
	latest = getdate(add_days(today, cint(settings.update_future_n_dates)))
	if not earliest <= getdate(actual_date) <= latest:
		frappe.throw(
			_("Actual date {0} is outside the allowed range {1} to {2}.").format(
				format_date(actual_date), format_date(earliest), format_date(latest)
			)
		)
