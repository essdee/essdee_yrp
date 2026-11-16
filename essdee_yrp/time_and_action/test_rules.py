import frappe
from frappe.utils import add_days, getdate, nowdate

from essdee_yrp.time_and_action.create import create_time_and_action
from essdee_yrp.time_and_action.testing import (
	TimeAndActionTestCase,
	make_lot,
	make_master,
	use_company_holidays,
)

STEPS = [("TA-TEST-YARN", 2), ("TA-TEST-TRIMS", 1), ("TA-TEST-KNIT", 3), ("TA-TEST-CUT", 1)]
DEPENDENCIES = {"TA-TEST-KNIT": ["TA-TEST-YARN"], "TA-TEST-CUT": ["TA-TEST-KNIT", "TA-TEST-TRIMS"]}


def save_actuals(name, changes):
	"""Save `{action: actual_date | None}` the way the Update page does."""
	doc = frappe.get_doc("SD YRP Time and Action", name)
	for row in doc.details:
		if row.action in changes:
			row.actual_date = changes[row.action]
			row.reason = "late" if changes[row.action] else None
	frappe.flags.in_time_and_action_update = True
	try:
		doc.save()
	finally:
		frappe.flags.in_time_and_action_update = False
	return doc


def set_window(past_days, future_days):
	frappe.db.set_single_value("SD YRP T and A Settings", "update_last_n_dates", past_days)
	frappe.db.set_single_value("SD YRP T and A Settings", "update_future_n_dates", future_days)


class TestActualDateRules(TimeAndActionTestCase):
	def setUp(self):
		use_company_holidays([], "2025-01-01", "2028-12-31")
		set_window(3650, 3650)
		master = make_master(STEPS, DEPENDENCIES)
		self.name = create_time_and_action("SD YRP Lot", make_lot(), master.name, "2026-11-02")

	def test_actual_before_dependency_is_refused(self):
		save_actuals(self.name, {"TA-TEST-YARN": "2026-11-04"})
		with self.assertRaisesRegex(frappe.ValidationError, "04-11-2026"):
			save_actuals(self.name, {"TA-TEST-KNIT": "2026-11-03"})

	def test_actual_equal_to_latest_dependency_is_allowed(self):
		save_actuals(self.name, {"TA-TEST-YARN": "2026-11-04", "TA-TEST-TRIMS": "2026-11-06"})
		save_actuals(self.name, {"TA-TEST-KNIT": "2026-11-05"})
		with self.assertRaisesRegex(frappe.ValidationError, "06-11-2026"):
			save_actuals(self.name, {"TA-TEST-CUT": "2026-11-05"})
		doc = save_actuals(self.name, {"TA-TEST-CUT": "2026-11-06"})
		self.assertEqual(getdate(doc.details[-1].actual_date), getdate("2026-11-06"))

	def test_steps_without_dependencies_in_any_order(self):
		save_actuals(self.name, {"TA-TEST-TRIMS": "2026-11-03"})
		doc = save_actuals(self.name, {"TA-TEST-YARN": "2026-11-05"})
		self.assertEqual(doc.action, "TA-TEST-KNIT")

	def test_actual_with_undated_dependency_is_refused(self):
		save_actuals(self.name, {"TA-TEST-YARN": "2026-11-04"})
		with self.assertRaisesRegex(frappe.ValidationError, "TA-TEST-TRIMS"):
			save_actuals(self.name, {"TA-TEST-KNIT": "2026-11-05", "TA-TEST-CUT": "2026-11-06"})

	def test_change_actual_with_dated_successor_is_refused(self):
		save_actuals(self.name, {"TA-TEST-YARN": "2026-11-04"})
		save_actuals(self.name, {"TA-TEST-KNIT": "2026-11-05"})
		with self.assertRaisesRegex(frappe.ValidationError, "TA-TEST-KNIT"):
			save_actuals(self.name, {"TA-TEST-YARN": "2026-11-03"})
		with self.assertRaisesRegex(frappe.ValidationError, "TA-TEST-KNIT"):
			save_actuals(self.name, {"TA-TEST-YARN": None})

	def test_remove_actual_without_dated_successor_is_allowed(self):
		save_actuals(self.name, {"TA-TEST-YARN": "2026-11-04"})
		save_actuals(self.name, {"TA-TEST-KNIT": "2026-11-05"})
		doc = save_actuals(self.name, {"TA-TEST-KNIT": None, "TA-TEST-YARN": None})
		self.assertFalse(any(row.actual_date for row in doc.details))
		self.assertEqual(doc.action, "TA-TEST-YARN")

	def test_actual_dates_reschedule_pending_rows(self):
		doc = save_actuals(self.name, {"TA-TEST-YARN": "2026-11-10"})
		knit = next(row for row in doc.details if row.action == "TA-TEST-KNIT")
		self.assertEqual(getdate(knit.rescheduled_date), getdate("2026-11-13"))
		self.assertEqual(getdate(knit.date), getdate("2026-11-07"))
		self.assertEqual(getdate(doc.end_date), getdate("2026-11-14"))
		self.assertLess(doc.delay, 0)

	def test_desk_save_of_actual_date_is_refused(self):
		doc = frappe.get_doc("SD YRP Time and Action", self.name)
		doc.details[0].actual_date = "2026-11-04"
		with self.assertRaisesRegex(frappe.ValidationError, "Update page"):
			doc.save()

	def test_frozen_ta_is_read_only(self):
		frappe.db.set_value("SD YRP Time and Action", self.name, "status", "Frozen")
		with self.assertRaisesRegex(frappe.ValidationError, "Frozen"):
			save_actuals(self.name, {"TA-TEST-YARN": "2026-11-04"})

	def test_late_actual_without_reason_is_refused(self):
		doc = frappe.get_doc("SD YRP Time and Action", self.name)
		doc.details[0].actual_date = "2026-11-05"
		frappe.flags.in_time_and_action_update = True
		with self.assertRaisesRegex(frappe.ValidationError, "reason"):
			doc.save()

	def test_actual_outside_window_is_refused(self):
		set_window(2, 0)
		with self.assertRaisesRegex(frappe.ValidationError, "allowed"):
			save_actuals(self.name, {"TA-TEST-YARN": add_days(nowdate(), 1)})
