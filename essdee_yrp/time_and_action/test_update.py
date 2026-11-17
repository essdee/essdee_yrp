import json

import frappe
from frappe.utils import get_datetime, getdate, now_datetime

from essdee_yrp.time_and_action.create import create_time_and_action
from essdee_yrp.time_and_action.test_rules import DEPENDENCIES, STEPS, set_window
from essdee_yrp.time_and_action.testing import (
	TimeAndActionTestCase,
	make_lot,
	make_master,
	use_company_holidays,
)
from essdee_yrp.time_and_action.update import (
	complete_time_and_action,
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

	def test_running_delay_counts_working_days_late_as_negative(self):
		use_company_holidays(["2026-11-12", "2026-11-13"], "2025-01-01", "2028-12-31")
		update_actual_dates(self.name, [change("TA-TEST-YARN", "2026-11-10", "late")], self.modified())
		doc = frappe.get_doc(TIME_AND_ACTION, self.name)
		self.assertEqual(getdate(doc.details[-1].planned_start_date), getdate("2026-11-08"))
		self.assertEqual(getdate(doc.end_date), getdate("2026-11-16"))
		self.assertEqual(doc.delay, -6)
		self.assertEqual(get_update_data(self.name)["delay"], -6)

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

	def test_on_time_row_keeps_optional_remarks(self):
		update_actual_dates(self.name, [change("TA-TEST-YARN", "2026-11-03", "Fabric checked early")], self.modified())
		doc = frappe.get_doc(TIME_AND_ACTION, self.name)
		self.assertEqual(doc.details[0].reason, "Fabric checked early")
		update_actual_dates(self.name, [change("TA-TEST-TRIMS", None, "Supplier confirmed")], self.modified())
		trims = next(row for row in frappe.get_doc(TIME_AND_ACTION, self.name).details if row.action == "TA-TEST-TRIMS")
		self.assertEqual(trims.reason, "Supplier confirmed")

	def test_update_data_flags_auto_actual_dates(self):
		doc = frappe.get_doc(TIME_AND_ACTION, self.name)
		frappe.db.set_value(doc.details[0].doctype, doc.details[0].name, "auto_actual_date", 1)
		rows = get_update_data(self.name)["rows"]
		self.assertEqual(rows[0]["auto_actual_date"], 1)
		self.assertEqual(rows[1]["auto_actual_date"], 0)

	def test_unknown_action_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			update_actual_dates(self.name, [change("NOT-A-STEP", "2026-11-04")], self.modified())

	def date_all(self):
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

	def complete(self):
		self.date_all()
		complete_time_and_action(self.name)

	def status(self):
		return frappe.db.get_value(TIME_AND_ACTION, self.name, "status")

	def test_dating_last_action_does_not_complete(self):
		self.date_all()
		self.assertEqual(self.status(), "In Progress")
		self.assertTrue(get_update_data(self.name)["can_complete"])

	def test_complete_requires_every_actual_date(self):
		update_actual_dates(self.name, [change("TA-TEST-YARN", "2026-11-04")], self.modified())
		self.assertFalse(get_update_data(self.name)["can_complete"])
		with self.assertRaisesRegex(frappe.ValidationError, "TA-TEST-TRIMS"):
			complete_time_and_action(self.name)
		self.assertEqual(self.status(), "In Progress")

	def test_complete_through_frappe_call(self):
		self.date_all()
		frappe.call("essdee_yrp.time_and_action.update.complete_time_and_action", time_and_action=self.name)
		self.assertEqual(self.status(), "Completed")
		self.assertFalse(get_update_data(self.name)["can_complete"])

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

	def test_desk_save_cannot_change_status(self):
		self.complete()
		doc = frappe.get_doc(TIME_AND_ACTION, self.name)
		doc.status = "In Progress"
		with self.assertRaisesRegex(frappe.ValidationError, "Reopen"):
			doc.save()

	def test_system_manager_reopens_keeping_dates(self):
		self.complete()
		frappe.set_user(make_user("System Manager"))
		self.assertTrue(get_update_data(self.name)["can_reopen"])
		reopen_time_and_action(self.name)
		doc = frappe.get_doc(TIME_AND_ACTION, self.name)
		self.assertEqual(doc.status, "In Progress")
		self.assertEqual(getdate(doc.details[-1].actual_date), getdate("2026-11-08"))
		update_actual_dates(self.name, [change("TA-TEST-CUT", "2026-11-09", "late")], self.modified())

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


class TestReviseDatesLog(TimeAndActionTestCase):
	def setUp(self):
		use_company_holidays([], "2025-01-01", "2028-12-31")
		set_window(3650, 3650)
		frappe.db.set_single_value("SD YRP T and A Settings", "revised_date_approver_role", "System Manager")
		frappe.db.set_single_value("SD YRP T and A Settings", "revising_days_limit", 5)
		master = make_master(STEPS, DEPENDENCIES)
		self.name = create_time_and_action("SD YRP Lot", make_lot(), master.name, "2026-11-02")

	def delay_and_revise(self, action, actual_date, reason):
		modified = str(frappe.db.get_value(TIME_AND_ACTION, self.name, "modified"))
		update_actual_dates(self.name, [change(action, actual_date, "late")], modified)
		doc = frappe.get_doc(TIME_AND_ACTION, self.name)
		expected = [
			(row.action, row.planned_start_date, row.date, row.rescheduled_date) for row in doc.details
		]
		revise_dates(self.name, reason)
		return expected

	def assert_log(self, rows, revision_no, expected, reason, started):
		for row, (action, planned, previous, frozen) in zip(rows, expected, strict=True):
			self.assertEqual(row.revision_no, revision_no)
			self.assertEqual(row.action, action)
			self.assertEqual(getdate(row.planned_date), getdate(planned))
			self.assertEqual(getdate(row.from_date), getdate(previous))
			self.assertEqual(getdate(row.to_date), getdate(frozen))
			self.assertEqual(row.user, "Administrator")
			self.assertEqual(row.reason, reason)
			self.assertGreaterEqual(get_datetime(row.revised_on), started)

	def test_each_revision_appends_one_row_per_action(self):
		started = now_datetime().replace(microsecond=0)
		first = self.delay_and_revise("TA-TEST-YARN", "2026-11-10", "yarn late")
		second = self.delay_and_revise("TA-TEST-KNIT", "2026-11-16", "knitting late")
		doc = frappe.get_doc(TIME_AND_ACTION, self.name)
		count = len(doc.details)
		self.assertEqual(doc.revised, 2)
		self.assertEqual(len(doc.time_and_action_revised_dates), 2 * count)
		self.assertNotEqual(first[-1][3], second[-1][3])
		self.assert_log(doc.time_and_action_revised_dates[:count], 1, first, "yarn late", started)
		self.assert_log(doc.time_and_action_revised_dates[count:], 2, second, "knitting late", started)
		self.assertEqual(getdate(doc.details[-1].date), getdate(second[-1][3]))

	def test_desk_save_cannot_change_log_row(self):
		self.delay_and_revise("TA-TEST-YARN", "2026-11-10", "yarn late")
		doc = frappe.get_doc(TIME_AND_ACTION, self.name)
		doc.time_and_action_revised_dates[0].reason = "edited"
		with self.assertRaisesRegex(frappe.ValidationError, "Revision History"):
			doc.save()

	def test_desk_save_cannot_remove_log_row(self):
		self.delay_and_revise("TA-TEST-YARN", "2026-11-10", "yarn late")
		doc = frappe.get_doc(TIME_AND_ACTION, self.name)
		doc.time_and_action_revised_dates.pop()
		with self.assertRaisesRegex(frappe.ValidationError, "Revision History"):
			doc.save()

	def test_desk_save_cannot_add_log_row(self):
		doc = frappe.get_doc(TIME_AND_ACTION, self.name)
		doc.append("time_and_action_revised_dates", {"action": "TA-TEST-YARN", "reason": "forged"})
		with self.assertRaisesRegex(frappe.ValidationError, "Revision History"):
			doc.save()

	def test_revise_through_frappe_call(self):
		frappe.call(
			"essdee_yrp.time_and_action.update.revise_dates",
			time_and_action=self.name,
			reason="customer moved delivery",
		)
		doc = frappe.get_doc(TIME_AND_ACTION, self.name)
		self.assertEqual(doc.revised, 1)
		self.assertEqual({row.revision_no for row in doc.time_and_action_revised_dates}, {1})
		self.assertEqual(len(doc.time_and_action_revised_dates), len(doc.details))


def make_user(*roles):
	email = f"ta-test-{frappe.generate_hash(length=6)}@example.com"
	user = frappe.get_doc(
		{"doctype": "User", "email": email, "first_name": "TA Test", "send_welcome_email": 0}
	)
	user.insert(ignore_permissions=True)
	user.add_roles(*roles)
	return email
