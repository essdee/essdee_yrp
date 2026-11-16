import frappe

from essdee_yrp.essdee_yrp.doctype.sd_yrp_time_and_action_gantt_chart.sd_yrp_time_and_action_gantt_chart import (
	get_chart_data,
)
from essdee_yrp.purchase.lot_editor import _lot_locks
from essdee_yrp.time_and_action.create import create_time_and_action
from essdee_yrp.time_and_action.reports import (
	execute_cumulative_time_and_action_delay,
	execute_live_time_and_action_delay,
	execute_time_and_action_delay_analysis,
	execute_time_and_action_department_performance,
	execute_time_and_action_dispatch_report,
	execute_time_and_action_pending_work,
	execute_time_and_action_report,
	execute_time_and_action_summary,
)
from essdee_yrp.time_and_action.test_rules import DEPENDENCIES, STEPS, save_actuals, set_window
from essdee_yrp.time_and_action.testing import (
	TimeAndActionTestCase,
	make_lot,
	make_master,
	use_company_holidays,
)
from essdee_yrp.time_and_action.tracking import (
	get_t_and_a_report_data,
	get_t_and_a_review_report_data,
)
from essdee_yrp.time_and_action.work_station import get_work_stations

PROVIDERS = (
	execute_cumulative_time_and_action_delay,
	execute_live_time_and_action_delay,
	execute_time_and_action_department_performance,
	execute_time_and_action_dispatch_report,
	execute_time_and_action_report,
	execute_time_and_action_summary,
)


class TestTimeAndActionReaders(TimeAndActionTestCase):
	def setUp(self):
		use_company_holidays([], "2025-01-01", "2028-12-31")
		set_window(3650, 3650)
		self.lot = make_lot()
		master = make_master(STEPS, DEPENDENCIES)
		self.name = create_time_and_action("SD YRP Lot", self.lot, master.name, "2026-11-02")
		save_actuals(self.name, {"TA-TEST-YARN": "2026-11-05"})

	def test_all_time_and_action_report_providers_execute(self):
		for provider in PROVIDERS:
			for filters in ({}, {"lot": self.lot}):
				result = provider(filters)
				self.assertIsInstance(result[1], list, provider.__name__)
		rows = execute_time_and_action_report({"lot": self.lot})[1]
		self.assertEqual([(row.against, row.against_id) for row in rows], [("SD YRP Lot", self.lot)])
		pending = execute_time_and_action_pending_work({"date": "2026-12-31"})[1]
		self.assertIn(self.lot, {row.against_id for row in pending})
		analysis = execute_time_and_action_delay_analysis({"lot": self.lot, "time_and_action": self.name})
		self.assertEqual([row.action for row in analysis[1]], ["TA-TEST-YARN"])

	def test_frozen_ta_is_excluded_from_reports(self):
		frappe.db.set_value("SD YRP Time and Action", self.name, "status", "Frozen")
		self.assertEqual(execute_time_and_action_dispatch_report({"lot": self.lot})[1], [])
		self.assertEqual(execute_time_and_action_summary({"lot": self.lot})[1], [])

	def test_gantt_lists_pending_rows_of_active_ta(self):
		items = get_chart_data("TA-TEST-KNIT")
		self.assertIn(f"{self.lot}-", " ".join(item["name"] for item in items))
		self.assertTrue(all(set(item) == {"id", "name", "start", "end", "progress"} for item in items))

	def test_tracking_and_review_providers(self):
		tracking = get_t_and_a_report_data()
		self.assertEqual(set(tracking), {"row_keys", "dates", "datas"})
		review = get_t_and_a_review_report_data(lot=self.lot)
		data = next(iter(review[self.lot].values()))
		self.assertEqual(data["datas"][0]["name"], self.name)

	def test_work_station_editor_reads_one_ta(self):
		self.assertEqual(list(get_work_stations(self.name)), [self.name])

	def test_lot_onload_shows_next_pending_step(self):
		lot = frappe.get_doc("SD YRP Lot", self.lot)
		self.assertEqual(lot.time_and_action, self.name)
		self.assertTrue(lot.has_time_and_action)
		lot.run_method("onload")
		details = lot.get("__onload").get("action_details")
		self.assertEqual(details[0]["action"], "TA-TEST-TRIMS")
		self.assertEqual(lot.get("__onload").get("time_and_action"), self.name)

	def test_lot_editor_locks_order_details_when_ta_exists(self):
		lot = frappe.get_doc("SD YRP Lot", self.lot)
		self.assertTrue(_lot_locks(lot, False, False)["order_details"])
		self.assertFalse(_lot_locks(frappe.get_doc("SD YRP Lot", make_lot()), False, False)["order_details"])
