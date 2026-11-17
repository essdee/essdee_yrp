import frappe
from frappe.utils import getdate

from essdee_yrp.time_and_action.create import create_time_and_action
from essdee_yrp.time_and_action.finishing_dates import (
	apply_packing_goods_received_note,
	is_packing_threshold_met,
)
from essdee_yrp.time_and_action.test_rules import DEPENDENCIES, STEPS, save_actuals, set_window
from essdee_yrp.time_and_action.testing import (
	TimeAndActionTestCase,
	make_lot,
	make_master,
	use_company_holidays,
)

TIME_AND_ACTION = "SD YRP Time and Action"
GROUP = "Ironing and Packing"
PROCESSES = {"TA-TEST-YARN": "Ironing", "TA-TEST-TRIMS": "Packing", "TA-TEST-KNIT": GROUP}
POSTING_DATE = "2026-11-05"


class TestFinishingActualDate(TimeAndActionTestCase):
	def setUp(self):
		self.work_order = frappe.db.get_value("YRP Work Order", {"process_name": GROUP}, "name")
		if not self.work_order:
			self.skipTest(f"No {GROUP} Work Order on this site")
		use_company_holidays([], "2025-01-01", "2028-12-31")
		set_window(3650, 3650)
		frappe.db.set_single_value("SD YRP MRP Settings", "ta_actual_date_percentage", 90)
		master = make_master(STEPS, DEPENDENCIES)
		for action, process_name in PROCESSES.items():
			frappe.db.set_value("SD YRP Action", action, "process_name", process_name)
		self.lot = make_lot()
		self.name = create_time_and_action("SD YRP Lot", self.lot, master.name, "2026-11-02")

	def plan(self, packed_boxes):
		doc = frappe.new_doc("SD YRP Finishing Plan")
		doc.update({"lot": self.lot, "work_order": self.work_order, "pieces_per_box": 10})
		doc.append("finishing_plan_details", {"item_variant": "TA-TEST-M", "cutting_qty": 100})
		doc.append("finishing_plan_grn_details", {"item_variant": "TA-TEST-M", "quantity": packed_boxes})
		return doc

	def apply(self, packed_boxes, cancelled=False, **grn):
		grn = frappe._dict({"includes_packing": 1, "posting_date": POSTING_DATE, **grn})
		apply_packing_goods_received_note(self.plan(packed_boxes), grn, cancelled)

	def actual_dates(self):
		doc = frappe.get_doc(TIME_AND_ACTION, self.name)
		return {row.action: row.actual_date and str(getdate(row.actual_date)) for row in doc.details}

	def test_threshold_met_dates_ironing_packing_and_group_alike(self):
		self.apply(9)
		dates = self.actual_dates()
		for action in PROCESSES:
			self.assertEqual(dates[action], POSTING_DATE)
		self.assertIsNone(dates["TA-TEST-CUT"])

	def test_below_threshold_sets_nothing(self):
		self.apply(8)
		self.assertFalse(any(self.actual_dates().values()))

	def test_return_grn_does_not_set(self):
		self.apply(9, is_return=1)
		self.assertFalse(any(self.actual_dates().values()))

	def test_cancel_that_drops_below_clears(self):
		self.apply(9)
		self.apply(9, cancelled=True)
		self.assertEqual(self.actual_dates()["TA-TEST-TRIMS"], POSTING_DATE)
		self.apply(5, cancelled=True)
		self.assertFalse(any(self.actual_dates().values()))

	def test_feature_off_sets_nothing(self):
		frappe.db.set_single_value("SD YRP MRP Settings", "ta_actual_date_percentage", None)
		self.apply(10)
		self.assertFalse(any(self.actual_dates().values()))

	def test_manual_date_is_untouched(self):
		save_actuals(self.name, {"TA-TEST-YARN": "2026-11-03"})
		self.apply(9)
		self.assertEqual(self.actual_dates()["TA-TEST-YARN"], "2026-11-03")
		self.assertEqual(self.actual_dates()["TA-TEST-TRIMS"], POSTING_DATE)
		self.apply(0, cancelled=True)
		dates = self.actual_dates()
		self.assertEqual(dates["TA-TEST-YARN"], "2026-11-03")
		self.assertIsNone(dates["TA-TEST-TRIMS"])


class TestPackingThreshold(TimeAndActionTestCase):
	def test_threshold(self):
		self.assertTrue(is_packing_threshold_met(90, 100, 90))
		self.assertTrue(is_packing_threshold_met(120, 100, 90))
		self.assertFalse(is_packing_threshold_met(89, 100, 90))

	def test_no_cutting_total_is_never_met(self):
		self.assertFalse(is_packing_threshold_met(10, 0, 90))
