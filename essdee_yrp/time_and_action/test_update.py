import json

import frappe
from frappe.utils import getdate

from essdee_yrp.time_and_action.create import create_time_and_action
from essdee_yrp.time_and_action.test_rules import DEPENDENCIES, STEPS, set_window
from essdee_yrp.time_and_action.testing import (
	TimeAndActionTestCase,
	make_lot,
	make_master,
	use_company_holidays,
)
from essdee_yrp.time_and_action.update import (
	get_update_data,
	preview_actual_dates,
	reopen_time_and_action,
	revert_time_and_action,
	revise_dates,
	update_actual_dates,
)

TIME_AND_ACTION = "SD YRP Time and Action"


def change(action, actual_date, reason=None):
	return {"action": action, "actual_date": actual_date, "reason": reason}


class TestUpdateActualDates(TimeAndActionTestCase):
	def setUp(self):
		use_company_holidays([], "2025-01-01", "2028-12-31")
		set_window(3650, 3650)
		master = make_master(STEPS, DEPENDENCIES)
		self.name = create_time_and_action("SD YRP Lot", make_lot(), master.name, "2026-11-02")

	def modified(self):
		return str(frappe.db.get_value(TIME_AND_ACTION, self.name, "modified"))

	def test_update_saves_and_reschedules(self):
		update_actual_dates(self.name, [change("TA-TEST-YARN", "2026-11-10", "yarn late")], self.modified())
		doc = frappe.get_doc(TIME_AND_ACTION, self.name)
		knit = next(row for row in doc.details if row.action == "TA-TEST-KNIT")
		self.assertEqual(getdate(doc.details[0].actual_date), getdate("2026-11-10"))
		self.assertEqual(doc.details[0].reason, "yarn late")
		self.assertEqual(getdate(knit.rescheduled_date), getdate("2026-11-13"))

	def test_update_with_stale_modified_is_refused(self):
		stale = self.modified()
		update_actual_dates(self.name, [change("TA-TEST-TRIMS", "2026-11-03")], stale)
		with self.assertRaisesRegex(frappe.ValidationError, "Refresh"):
			update_actual_dates(self.name, [change("TA-TEST-YARN", "2026-11-04")], stale)

	def test_preview_does_not_save(self):
		result = preview_actual_dates(
			self.name, [change("TA-TEST-YARN", "2026-11-10", "late")], self.modified()
		)
		knit = next(row for row in result["rows"] if row["action"] == "TA-TEST-KNIT")
		self.assertEqual(getdate(knit["rescheduled_date"]), getdate("2026-11-13"))
		self.assertTrue(knit["can_enter"])
		self.assertIsNone(frappe.get_doc(TIME_AND_ACTION, self.name).details[0].actual_date)

	def test_preview_allows_late_date_before_reason_is_typed(self):
		result = preview_actual_dates(self.name, [change("TA-TEST-YARN", "2026-11-10")], self.modified())
		self.assertEqual(str(result["rows"][0]["actual_date"]), "2026-11-10")
		with self.assertRaisesRegex(frappe.ValidationError, "reason"):
			update_actual_dates(self.name, [change("TA-TEST-YARN", "2026-11-10")], self.modified())

	def test_preview_reports_delivery_moving_later_in_working_days(self):
		use_company_holidays(["2026-11-12"], "2025-01-01", "2028-12-31")
		result = preview_actual_dates(self.name, [change("TA-TEST-YARN", "2026-11-10")], self.modified())
		self.assertEqual(getdate(result["delivery_date_before"]), getdate("2026-11-08"))
		self.assertEqual(getdate(result["delivery_date_after"]), getdate("2026-11-15"))
		self.assertEqual(result["delivery_days_moved"], 6)

	def test_preview_reports_unchanged_delivery(self):
		result = preview_actual_dates(self.name, [change("TA-TEST-TRIMS", "2026-11-03")], self.modified())
		self.assertEqual(getdate(result["delivery_date_before"]), getdate("2026-11-08"))
		self.assertEqual(getdate(result["delivery_date_after"]), getdate("2026-11-08"))
		self.assertEqual(result["delivery_days_moved"], 0)

	def test_preview_reports_delivery_pulled_in(self):
		result = preview_actual_dates(self.name, [change("TA-TEST-YARN", "2026-11-03")], self.modified())
		self.assertEqual(getdate(result["delivery_date_after"]), getdate("2026-11-07"))
		self.assertEqual(result["delivery_days_moved"], -1)

	def test_preview_accepts_json_string_args_from_desk(self):
		result = frappe.call(
			"essdee_yrp.time_and_action.update.preview_actual_dates",
			time_and_action=self.name,
			changes=json.dumps([change("TA-TEST-YARN", "2026-11-10")]),
			modified=self.modified(),
		)
		self.assertEqual(result["delivery_days_moved"], 6)

	def test_preview_runs_the_rules(self):
		with self.assertRaisesRegex(frappe.ValidationError, "TA-TEST-YARN"):
			preview_actual_dates(self.name, [change("TA-TEST-KNIT", "2026-11-05")], self.modified())

	def test_update_data_flags_follow_rules(self):
		update_actual_dates(self.name, [change("TA-TEST-YARN", "2026-11-04")], self.modified())
		update_actual_dates(self.name, [change("TA-TEST-KNIT", "2026-11-07")], self.modified())
		rows = {row["action"]: row for row in get_update_data(self.name)["rows"]}
		self.assertFalse(rows["TA-TEST-YARN"]["can_remove"])
		self.assertTrue(rows["TA-TEST-KNIT"]["can_remove"])
		self.assertTrue(rows["TA-TEST-TRIMS"]["can_enter"])
		self.assertFalse(rows["TA-TEST-CUT"]["can_enter"])
		self.assertEqual(rows["TA-TEST-CUT"]["depends_on"]["TA-TEST-KNIT"], getdate("2026-11-07"))

	def test_unknown_action_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			update_actual_dates(self.name, [change("NOT-A-STEP", "2026-11-04")], self.modified())

	def complete(self):
		update_actual_dates(
			self.name,
			[
				change("TA-TEST-YARN", "2026-11-04"),
				change("TA-TEST-TRIMS", "2026-11-05"),
				change("TA-TEST-KNIT", "2026-11-07"),
				change("TA-TEST-CUT", "2026-11-08"),
			],
			self.modified(),
		)

	def status(self):
		return frappe.db.get_value(TIME_AND_ACTION, self.name, "status")

	def test_last_actual_date_completes(self):
		update_actual_dates(
			self.name,
			[change("TA-TEST-YARN", "2026-11-04"), change("TA-TEST-TRIMS", "2026-11-05")],
			self.modified(),
		)
		update_actual_dates(self.name, [change("TA-TEST-KNIT", "2026-11-07")], self.modified())
		self.assertEqual(self.status(), "In Progress")
		update_actual_dates(self.name, [change("TA-TEST-CUT", "2026-11-08")], self.modified())
		self.assertEqual(self.status(), "Completed")

	def test_completed_refuses_actual_date_changes(self):
		self.complete()
		with self.assertRaisesRegex(frappe.ValidationError, "Completed"):
			update_actual_dates(self.name, [change("TA-TEST-CUT", "2026-11-09", "late")], self.modified())
		with self.assertRaisesRegex(frappe.ValidationError, "Completed"):
			preview_actual_dates(self.name, [change("TA-TEST-CUT", None)], self.modified())

	def test_completed_refuses_revise(self):
		self.complete()
		self.assertFalse(get_update_data(self.name)["can_revise"])
		with self.assertRaises(frappe.PermissionError):
			revise_dates(self.name, "customer moved delivery")

	def test_desk_save_cannot_reset_status(self):
		self.complete()
		doc = frappe.get_doc(TIME_AND_ACTION, self.name)
		doc.status = "In Progress"
		doc.save()
		self.assertEqual(self.status(), "Completed")

	def test_system_manager_reopens(self):
		self.complete()
		frappe.set_user(make_user("System Manager"))
		self.assertTrue(get_update_data(self.name)["can_reopen"])
		reopen_time_and_action(self.name)
		doc = frappe.get_doc(TIME_AND_ACTION, self.name)
		self.assertEqual(doc.status, "In Progress")
		self.assertIsNone(doc.details[-1].actual_date)
		self.assertEqual(getdate(doc.details[-2].actual_date), getdate("2026-11-07"))
		update_actual_dates(self.name, [change("TA-TEST-CUT", "2026-11-09", "late")], self.modified())
		self.assertEqual(self.status(), "Completed")

	def test_reopen_refused_without_system_manager(self):
		self.complete()
		frappe.set_user(make_user("T & A User", "T & A Admin"))
		self.assertFalse(get_update_data(self.name)["can_reopen"])
		with self.assertRaises(frappe.PermissionError):
			reopen_time_and_action(self.name)
		self.assertEqual(self.status(), "Completed")

	def test_reopen_refused_when_not_completed(self):
		with self.assertRaisesRegex(frappe.ValidationError, "not Completed"):
			reopen_time_and_action(self.name)

	def test_reopen_through_frappe_call(self):
		self.complete()
		frappe.call("essdee_yrp.time_and_action.update.reopen_time_and_action", time_and_action=self.name)
		self.assertEqual(self.status(), "In Progress")

	def test_revert_requires_ta_admin(self):
		update_actual_dates(self.name, [change("TA-TEST-YARN", "2026-11-04")], self.modified())
		frappe.set_user(make_user("T & A User", "System Manager"))
		with self.assertRaises(frappe.PermissionError):
			revert_time_and_action(self.name)
		frappe.set_user(make_user("T & A User", "T & A Admin"))
		revert_time_and_action(self.name)
		self.assertFalse(frappe.db.exists(TIME_AND_ACTION, self.name))


def make_user(*roles):
	email = f"ta-test-{frappe.generate_hash(length=6)}@example.com"
	user = frappe.get_doc(
		{"doctype": "User", "email": email, "first_name": "TA Test", "send_welcome_email": 0}
	)
	user.insert(ignore_permissions=True)
	user.add_roles(*roles)
	return email
