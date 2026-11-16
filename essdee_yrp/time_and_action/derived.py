"""Derived dates and delays of a Time and Action, recomputed from its rows on every save."""

from frappe.utils import getdate

from essdee_yrp.time_and_action.holidays import HolidayCalendar, get_company_holidays
from essdee_yrp.time_and_action.schedule import (
	ScheduleRow,
	build_schedule,
	get_performance,
	get_working_day_diff,
)


def get_dependencies(doc) -> dict[str, list[str]]:
	dependencies = {}
	for row in doc.dependent_details:
		dependencies.setdefault(row.action, []).append(row.dependent_action)
	return dependencies


def apply_schedule(doc) -> None:
	holidays = get_company_holidays()
	rows = [ScheduleRow(row.action, row.lead_time, row.actual_date or None) for row in doc.details]
	schedule = build_schedule(rows, get_dependencies(doc), doc.start_date, holidays)
	for row in doc.details:
		set_row_dates(row, schedule[row.action], holidays)
	actual_dates = {row.action: row.actual_date for row in doc.details}
	for row in doc.dependent_details:
		row.dependent_action_date = actual_dates.get(row.dependent_action) or None
	set_summary(doc, holidays)


def set_row_dates(row, expected, holidays: HolidayCalendar) -> None:
	if not row.actual_date:
		row.update(
			{
				"rescheduled_date": expected,
				"rescheduled_start_date": expected,
				"completed": 0,
				"date_diff": 0,
				"performance": 0,
				"actual_delay": 0,
			}
		)
		return
	date_difference = get_working_day_diff(row.rescheduled_date, row.actual_date, holidays)
	row.update(
		{
			"completed": 1,
			"date_diff": date_difference,
			"performance": get_performance(date_difference),
			"actual_delay": get_working_day_diff(row.planned_start_date, row.actual_date, holidays),
		}
	)


def set_summary(doc, holidays: HolidayCalendar) -> None:
	"""Next pending action, expected end date and end-date delays (negative = late)."""
	pending = [row.action for row in doc.details if not row.actual_date]
	last = doc.details[-1]
	expected_end = getdate(last.actual_date or last.rescheduled_date)
	doc.action = pending[0] if pending else None
	doc.end_date = expected_end
	doc.delay = get_working_day_diff(last.planned_start_date, expected_end, holidays)
	doc.rescheduled_delay = get_working_day_diff(last.date, expected_end, holidays)
