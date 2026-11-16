"""Time and Action date engine: start date + lead times + company holidays."""

from dataclasses import dataclass
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, getdate

from essdee_yrp.time_and_action.holidays import HolidayCalendar


@dataclass
class ScheduleRow:
	action: str
	lead_time: int
	actual_date: date | None = None


def get_next_date(day, lead_time: int, holidays: HolidayCalendar) -> date:
	"""Add `lead_time` days, then push past every holiday crossed on the way."""
	start = getdate(day)
	result = getdate(add_days(start, int(lead_time or 0)))
	holidays.ensure_covers(start)
	while True:
		holidays.ensure_covers(result)
		skipped = holidays.count_between(start, result)
		if not skipped:
			return result
		start, result = result, getdate(add_days(result, skipped))


def get_working_day_diff(from_date, to_date, holidays: HolidayCalendar) -> int:
	"""`from_date - to_date` in days, minus the holidays between them."""
	from_date, to_date = getdate(from_date), getdate(to_date)
	diff = date_diff(from_date, to_date)
	skipped = holidays.count_between(min(from_date, to_date), max(from_date, to_date))
	return diff + skipped if diff < 0 else diff - skipped


def build_schedule(
	rows: list[ScheduleRow], dependencies: dict[str, list[str]], start_date, holidays: HolidayCalendar
) -> dict[str, date]:
	"""Effective date per action: the actual date, else computed from dependencies or the previous row."""
	effective = {}
	previous = getdate(start_date)
	for row in rows:
		if row.actual_date:
			effective[row.action] = getdate(row.actual_date)
		else:
			effective[row.action] = get_next_date(
				_get_base_date(row.action, dependencies, effective, previous), row.lead_time, holidays
			)
		previous = effective[row.action]
	return effective


def _get_base_date(action, dependencies, effective, previous):
	depends_on = dependencies.get(action) or []
	missing = [name for name in depends_on if name not in effective]
	if missing:
		frappe.throw(_("{0} depends on {1}, which must come earlier.").format(action, ", ".join(missing)))
	return max((effective[name] for name in depends_on), default=previous)


def get_performance(diff: int) -> int:
	if diff < -3:
		return 25
	return {-3: 50, -2: 75, -1: 85}.get(diff, 100)
