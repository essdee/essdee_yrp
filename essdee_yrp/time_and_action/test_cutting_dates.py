import frappe
from frappe.utils import getdate

from essdee_yrp.time_and_action.create import create_time_and_action
from essdee_yrp.time_and_action.cutting_dates import (
	CUTTING_PLAN,
	apply_cutting_plan,
	get_cutting_end_date,
	is_cutting_completed,
	on_cancel,
)
from essdee_yrp.time_and_action.test_rules import DEPENDENCIES, STEPS, save_actuals, set_window
from essdee_yrp.time_and_action.testing import (
	TimeAndActionTestCase,
	make_lot,
	make_master,
	use_company_holidays,
)

TIME_AND_ACTION = "SD YRP Time and Action"
CUT = "TA-TEST-CUT"


def plan(cp_status, cutting_end_date):
	return frappe._dict(name="CP", cp_status=cp_status, cutting_end_date=cutting_end_date)


class TestCuttingDecision(TimeAndActionTestCase):
	def test_every_plan_must_be_completed(self):
		self.assertTrue(is_cutting_completed([plan("Completed", None), plan("Completed", None)]))
		self.assertFalse(is_cutting_completed([plan("Completed", None), plan("Partially Completed", None)]))
		self.assertFalse(is_cutting_completed([]))

	def test_end_date_is_latest_or_none_when_missing(self):
		plans = [plan("Completed", "2026-11-10"), plan("Completed", "2026-11-12")]
		self.assertEqual(get_cutting_end_date(plans), getdate("2026-11-12"))
		self.assertIsNone(get_cutting_end_date([*plans, plan("Completed", None)]))

	def test_hooks_are_registered(self):
		events = frappe.get_hooks("doc_events")[CUTTING_PLAN]
		self.assertIn(
			"essdee_yrp.time_and_action.cutting_dates.on_update_after_submit",
			events["on_update_after_submit"],
		)
		self.assertIn("essdee_yrp.time_and_action.cutting_dates.on_cancel", events["on_cancel"])


class TestCuttingActualDate(TimeAndActionTestCase):
	def setUp(self):
		use_company_holidays([], "2025-01-01", "2028-12-31")
		set_window(3650, 3650)
		frappe.db.set_single_value("SD YRP MRP Settings", "ta_actual_date_percentage", 90)
		master = make_master(STEPS, DEPENDENCIES)
		self.production_detail, cutting_process = frappe.db.get_value(
			"YRP Item Production Detail", {"cutting_process": ["is", "set"]}, ["name", "cutting_process"]
		)
		frappe.db.set_value("SD YRP Action", CUT, "process_name", cutting_process)
		self.lot = make_lot()
		self.name = create_time_and_action("SD YRP Lot", self.lot, master.name, "2026-11-02")
		save_actuals(
			self.name,
			{"TA-TEST-YARN": "2026-11-03", "TA-TEST-TRIMS": "2026-11-03", "TA-TEST-KNIT": "2026-11-06"},
		)
		self.plans = [
			self.make_plan("Completed", "2026-11-10"),
			self.make_plan("Completed", "2026-11-12"),
		]

	def make_plan(self, cp_status, cutting_end_date, docstatus=1):
		doc = frappe.new_doc(CUTTING_PLAN)
		doc.name = f"TA-TEST-CP-{frappe.generate_hash(length=8)}"
		doc.update(
			{
				"lot": self.lot,
				"production_detail": self.production_detail,
				"cp_status": cp_status,
				"cutting_end_date": cutting_end_date,
				"docstatus": docstatus,
			}
		)
		doc.db_insert()
		return doc.name

	def cut_row(self):
		return next(row for row in frappe.get_doc(TIME_AND_ACTION, self.name).details if row.action == CUT)

	def test_all_completed_sets_latest_end_date(self):
		self.make_plan("Cancelled", "2026-11-20", docstatus=2)
		apply_cutting_plan(self.plans[0])
		row = self.cut_row()
		self.assertEqual(getdate(row.actual_date), getdate("2026-11-12"))
		self.assertEqual(row.auto_actual_date, 1)

	def test_one_plan_not_completed_sets_nothing(self):
		self.make_plan("Partially Completed", "2026-11-11")
		apply_cutting_plan(self.plans[0])
		self.assertIsNone(self.cut_row().actual_date)

	def test_missing_end_date_sets_nothing(self):
		self.make_plan("Completed", None)
		apply_cutting_plan(self.plans[0])
		self.assertIsNone(self.cut_row().actual_date)

	def test_regressing_clears_auto_date(self):
		apply_cutting_plan(self.plans[0])
		frappe.db.set_value(CUTTING_PLAN, self.plans[1], "cp_status", "Partially Completed")
		apply_cutting_plan(self.plans[1])
		row = self.cut_row()
		self.assertIsNone(row.actual_date)
		self.assertEqual(row.auto_actual_date, 0)

	def test_cancelling_a_plan_reevaluates(self):
		self.make_plan("Completed", "2026-11-14")
		incomplete = self.make_plan("Partially Completed", "2026-11-11")
		apply_cutting_plan(self.plans[0])
		self.assertIsNone(self.cut_row().actual_date)
		frappe.db.set_value(CUTTING_PLAN, incomplete, {"docstatus": 2, "cp_status": "Cancelled"})
		on_cancel(frappe.get_doc(CUTTING_PLAN, incomplete))
		self.assertEqual(getdate(self.cut_row().actual_date), getdate("2026-11-14"))

	def test_manual_date_is_untouched(self):
		save_actuals(self.name, {CUT: "2026-11-08"})
		apply_cutting_plan(self.plans[0])
		frappe.db.set_value(CUTTING_PLAN, self.plans[1], "cp_status", "Partially Completed")
		apply_cutting_plan(self.plans[1])
		row = self.cut_row()
		self.assertEqual(getdate(row.actual_date), getdate("2026-11-08"))
		self.assertEqual(row.auto_actual_date, 0)

	def test_feature_off_does_nothing(self):
		frappe.db.set_single_value("SD YRP MRP Settings", "ta_actual_date_percentage", None)
		apply_cutting_plan(self.plans[0])
		self.assertIsNone(self.cut_row().actual_date)
