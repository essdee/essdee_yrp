import erpnext
import frappe
from frappe.utils import getdate

from essdee_yrp.time_and_action.holidays import HolidayCalendar, get_company_holidays
from essdee_yrp.time_and_action.schedule import (
	ScheduleRow,
	build_schedule,
	get_next_date,
	get_working_day_diff,
)
from essdee_yrp.time_and_action.testing import TimeAndActionTestCase, dates, use_company_holidays

NO_HOLIDAYS = HolidayCalendar(frozenset(), getdate("2026-01-01"), getdate("2027-12-31"))


class TestSchedule(TimeAndActionTestCase):
	def test_next_date_skips_company_holidays(self):
		use_company_holidays(["2026-11-07"])
		holidays = get_company_holidays()
		self.assertEqual(get_next_date(getdate("2026-11-06"), 2, holidays), getdate("2026-11-09"))

	def test_engine_throws_without_company_holiday_list(self):
		frappe.db.set_value("Company", erpnext.get_default_company(), "default_holiday_list", None)
		with self.assertRaisesRegex(frappe.ValidationError, "Default Holiday List"):
			get_company_holidays()

	def test_engine_throws_outside_holiday_list_range(self):
		use_company_holidays([], "2026-01-01", "2026-12-31")
		with self.assertRaisesRegex(frappe.ValidationError, "31-12-2026"):
			get_next_date(getdate("2026-12-30"), 5, get_company_holidays())

	def test_working_day_diff_ignores_holidays(self):
		holidays = HolidayCalendar(
			frozenset(dates("2026-11-08")), getdate("2026-01-01"), getdate("2027-12-31")
		)
		self.assertEqual(get_working_day_diff("2026-11-10", "2026-11-06", holidays), 3)
		self.assertEqual(get_working_day_diff("2026-11-06", "2026-11-10", holidays), -3)

	def test_schedule_uses_latest_dependency(self):
		rows = [
			ScheduleRow("A", 1, getdate("2026-11-01")),
			ScheduleRow("B", 1, getdate("2026-11-03")),
			ScheduleRow("C", 1, getdate("2026-11-02")),
			ScheduleRow("D", 2),
		]
		schedule = build_schedule(rows, {"D": ["A", "B", "C"]}, getdate("2026-10-30"), NO_HOLIDAYS)
		self.assertEqual(schedule["D"], getdate("2026-11-05"))

	def test_schedule_follows_actual_dates(self):
		deps = {"B": ["A"], "C": ["B"]}
		start = getdate("2026-11-02")
		planned = build_schedule(
			[ScheduleRow("A", 3), ScheduleRow("B", 2), ScheduleRow("C", 1)], deps, start, NO_HOLIDAYS
		)
		self.assertEqual(planned["C"], getdate("2026-11-08"))
		early = build_schedule(
			[ScheduleRow("A", 3, getdate("2026-11-03")), ScheduleRow("B", 2), ScheduleRow("C", 1)],
			deps,
			start,
			NO_HOLIDAYS,
		)
		self.assertEqual(early["C"], getdate("2026-11-06"))
		late = build_schedule(
			[ScheduleRow("A", 3, getdate("2026-11-10")), ScheduleRow("B", 2), ScheduleRow("C", 1)],
			deps,
			start,
			NO_HOLIDAYS,
		)
		self.assertEqual(late["C"], getdate("2026-11-13"))

	def test_schedule_chains_rows_without_dependencies(self):
		schedule = build_schedule(
			[ScheduleRow("A", 1), ScheduleRow("B", 2)], {}, getdate("2026-11-02"), NO_HOLIDAYS
		)
		self.assertEqual(schedule, {"A": getdate("2026-11-03"), "B": getdate("2026-11-05")})

	def test_schedule_matches_legacy_preview(self):
		"""Master-00001 from production with no holidays in the window."""
		steps = [
			("FILE", 1),
			("BUDGET", 2),
			("PLAN", 1),
			("FABRIC PO", 1),
			("TRIMS", 2),
			("FABRIC", 10),
			("SIZE SET", 4),
			("PP", 1),
			("CUTTING", 2),
			("EMB", 0),
			("SEWING", 7),
			("PACKING", 3),
			("DISPATCH", 1),
		]
		names = [name for name, _lead in steps]
		deps = {names[index]: [names[index - 1]] for index in range(1, len(names))}
		schedule = build_schedule(
			[ScheduleRow(n, lead) for n, lead in steps], deps, getdate("2026-08-18"), NO_HOLIDAYS
		)
		self.assertEqual(
			[schedule[name] for name in names],
			dates(
				"2026-08-19",
				"2026-08-21",
				"2026-08-22",
				"2026-08-23",
				"2026-08-25",
				"2026-09-04",
				"2026-09-08",
				"2026-09-09",
				"2026-09-11",
				"2026-09-11",
				"2026-09-18",
				"2026-09-21",
				"2026-09-22",
			),
		)
