import json

import frappe
from frappe.utils import getdate

from essdee_yrp.time_and_action.auto_date import (
	clear_auto_actual_date,
	get_actual_date_percentage,
	get_process_names,
	set_auto_actual_date,
)
from essdee_yrp.time_and_action.create import create_time_and_action
from essdee_yrp.time_and_action.test_rules import DEPENDENCIES, STEPS, save_actuals, set_window
from essdee_yrp.time_and_action.testing import (
	TimeAndActionTestCase,
	make_lot,
	make_master,
	use_company_holidays,
)
from essdee_yrp.time_and_action.update import update_actual_dates
from essdee_yrp.time_and_action.work_order_dates import is_threshold_met

TIME_AND_ACTION = "SD YRP Time and Action"
PROCESSES = {
	"TA-TEST-YARN": "Dyeing",
	"TA-TEST-TRIMS": "Printing",
	"TA-TEST-KNIT": "Knitting",
	"TA-TEST-CUT": "Cutting",
}


class TestAutoActualDate(TimeAndActionTestCase):
	def setUp(self):
		use_company_holidays([], "2025-01-01", "2028-12-31")
		set_window(3650, 3650)
		master = make_master(STEPS, DEPENDENCIES)
		for action, process_name in PROCESSES.items():
			frappe.db.set_value("SD YRP Action", action, "process_name", process_name)
		self.lot = make_lot()
		self.name = create_time_and_action("SD YRP Lot", self.lot, master.name, "2026-11-02")

	def rows(self):
		return {row.action: row for row in frappe.get_doc(TIME_AND_ACTION, self.name).details}

	def test_percentage_blank_is_off(self):
		frappe.db.set_single_value("SD YRP MRP Settings", "ta_actual_date_percentage", None)
		self.assertEqual(get_actual_date_percentage(), 0)
		frappe.db.set_single_value("SD YRP MRP Settings", "ta_actual_date_percentage", 90)
		self.assertEqual(get_actual_date_percentage(), 90)

	def test_set_marks_row_auto_and_late_reason_na(self):
		save_actuals(self.name, {"TA-TEST-YARN": "2026-11-04"})
		self.assertEqual(set_auto_actual_date(self.lot, ["Knitting"], "2026-11-20"), ["TA-TEST-KNIT"])
		knit = self.rows()["TA-TEST-KNIT"]
		self.assertEqual(getdate(knit.actual_date), getdate("2026-11-20"))
		self.assertEqual(knit.auto_actual_date, 1)
		self.assertEqual(knit.reason, "NA")
		self.assertEqual(getdate(self.rows()["TA-TEST-CUT"].rescheduled_date), getdate("2026-11-21"))

	def test_on_time_date_has_no_reason(self):
		set_auto_actual_date(self.lot, ["Printing"], "2026-11-02")
		trims = self.rows()["TA-TEST-TRIMS"]
		self.assertEqual(trims.auto_actual_date, 1)
		self.assertIsNone(trims.reason)

	def test_undated_dependency_is_skipped_silently(self):
		self.assertEqual(set_auto_actual_date(self.lot, ["Knitting"], "2026-11-20"), [])
		self.assertIsNone(self.rows()["TA-TEST-KNIT"].actual_date)
		self.assertFalse(frappe.local.message_log)

	def test_date_before_dependency_is_skipped(self):
		save_actuals(self.name, {"TA-TEST-YARN": "2026-11-10"})
		self.assertEqual(set_auto_actual_date(self.lot, ["Knitting"], "2026-11-05"), [])
		self.assertIsNone(self.rows()["TA-TEST-KNIT"].actual_date)

	def test_manual_date_is_kept(self):
		save_actuals(self.name, {"TA-TEST-YARN": "2026-11-04"})
		self.assertEqual(set_auto_actual_date(self.lot, ["Dyeing"], "2026-11-20"), [])
		yarn = self.rows()["TA-TEST-YARN"]
		self.assertEqual(getdate(yarn.actual_date), getdate("2026-11-04"))
		self.assertEqual(yarn.auto_actual_date, 0)

	def test_completed_and_frozen_are_skipped(self):
		for status in ("Completed", "Frozen"):
			frappe.db.set_value(TIME_AND_ACTION, self.name, "status", status)
			self.assertEqual(set_auto_actual_date(self.lot, ["Printing"], "2026-11-03"), [])
		self.assertIsNone(self.rows()["TA-TEST-TRIMS"].actual_date)

	def test_update_window_is_bypassed(self):
		set_window(0, 0)
		self.assertEqual(set_auto_actual_date(self.lot, ["Printing"], "2026-11-03"), ["TA-TEST-TRIMS"])

	def test_group_dates_every_mapped_action_once(self):
		self.assertEqual(
			set_auto_actual_date(self.lot, ["Dyeing", "Knitting"], "2026-11-04"),
			["TA-TEST-YARN", "TA-TEST-KNIT"],
		)

	def test_clear_touches_only_auto_rows(self):
		save_actuals(self.name, {"TA-TEST-YARN": "2026-11-04"})
		set_auto_actual_date(self.lot, ["Knitting"], "2026-11-20")
		self.assertEqual(clear_auto_actual_date(self.lot, ["Dyeing", "Knitting"]), ["TA-TEST-KNIT"])
		rows = self.rows()
		self.assertEqual(getdate(rows["TA-TEST-YARN"].actual_date), getdate("2026-11-04"))
		self.assertIsNone(rows["TA-TEST-KNIT"].actual_date)
		self.assertIsNone(rows["TA-TEST-KNIT"].reason)
		self.assertEqual(rows["TA-TEST-KNIT"].auto_actual_date, 0)

	def test_clear_skips_row_with_dated_successor(self):
		set_auto_actual_date(self.lot, ["Dyeing"], "2026-11-04")
		save_actuals(self.name, {"TA-TEST-KNIT": "2026-11-07"})
		self.assertEqual(clear_auto_actual_date(self.lot, ["Dyeing"]), [])
		self.assertEqual(getdate(self.rows()["TA-TEST-YARN"].actual_date), getdate("2026-11-04"))
		self.assertFalse(frappe.local.message_log)

	def test_clear_skips_completed(self):
		set_auto_actual_date(self.lot, ["Printing"], "2026-11-03")
		frappe.db.set_value(TIME_AND_ACTION, self.name, "status", "Completed")
		self.assertEqual(clear_auto_actual_date(self.lot, ["Printing"]), [])

	def test_manual_edit_clears_auto_flag(self):
		set_auto_actual_date(self.lot, ["Printing"], "2026-11-03")
		modified = str(frappe.db.get_value(TIME_AND_ACTION, self.name, "modified"))
		update_actual_dates(self.name, [{"action": "TA-TEST-TRIMS", "actual_date": "2026-11-02"}], modified)
		self.assertEqual(self.rows()["TA-TEST-TRIMS"].auto_actual_date, 0)
		self.assertEqual(clear_auto_actual_date(self.lot, ["Printing"]), [])

	def test_production_order_time_and_action_is_ignored(self):
		frappe.db.set_value(TIME_AND_ACTION, self.name, "against", "YRP Production Order")
		self.assertEqual(set_auto_actual_date(self.lot, ["Printing"], "2026-11-03"), [])


class TestProcessNames(TimeAndActionTestCase):
	def test_plain_process_is_itself(self):
		self.assertEqual(get_process_names("Knitting"), ["Knitting"])
		self.assertEqual(get_process_names(None), [])

	def test_group_adds_its_sub_processes(self):
		group = frappe.db.get_value("YRP Process", {"is_group": 1}, "name")
		sub_processes = frappe.get_all(
			"YRP Process Details", filters={"parent": group}, pluck="process_name", order_by="idx"
		)
		self.assertEqual(get_process_names(group), [group, *sub_processes])


def cut(variant, qty, set_combination=None):
	return {"item_variant": variant, "set_combination": set_combination, "cut_qty": qty}


def made(variant, delivered, received, set_combination=None):
	return {
		"item_variant": variant,
		"set_combination": set_combination,
		"delivered_quantity": delivered,
		"received_qty": received,
	}


class TestThreshold(TimeAndActionTestCase):
	def test_every_row_must_reach_percentage(self):
		cut_rows = [cut("RED-M", 100), cut("RED-L", 50)]
		self.assertTrue(is_threshold_met(cut_rows, [made("RED-M", 90, 90), made("RED-L", 45, 45)], 90))
		self.assertFalse(is_threshold_met(cut_rows, [made("RED-M", 100, 100), made("RED-L", 45, 44)], 90))
		self.assertFalse(is_threshold_met(cut_rows, [made("RED-M", 100, 100)], 90))

	def test_delivered_and_received_both_count(self):
		self.assertFalse(is_threshold_met([cut("RED-M", 100)], [made("RED-M", 80, 95)], 90))
		self.assertFalse(is_threshold_met([cut("RED-M", 100)], [made("RED-M", 95, 80)], 90))

	def test_work_orders_are_summed_by_set_combination(self):
		top = {"set_part": "Top", "major_colour": "Red"}
		bottom = {"major_colour": "Red", "set_part": "Bottom"}
		cut_rows = [cut("RED-M", 100, json.dumps(top)), cut("RED-M", 100, json.dumps(bottom))]
		made_rows = [
			made("RED-M", 50, 50, top),
			made("RED-M", 45, 45, json.dumps(dict(reversed(top.items())))),
			made("RED-M", 95, 95, bottom),
		]
		self.assertTrue(is_threshold_met(cut_rows, made_rows, 95))
		self.assertFalse(is_threshold_met(cut_rows, made_rows[1:], 95))

	def test_rows_without_cut_qty_are_ignored(self):
		self.assertTrue(is_threshold_met([cut("RED-M", 10), cut("RED-L", 0)], [made("RED-M", 10, 10)], 90))
		self.assertFalse(is_threshold_met([cut("RED-L", 0)], [], 90))
