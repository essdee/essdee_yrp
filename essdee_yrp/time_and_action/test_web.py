from unittest.mock import patch

import frappe

from essdee_yrp.time_and_action.create import create_time_and_action
from essdee_yrp.time_and_action.production_order import get_production_order_time_and_action
from essdee_yrp.time_and_action.test_create import submitted_production_order
from essdee_yrp.time_and_action.test_rules import DEPENDENCIES, STEPS, set_window
from essdee_yrp.time_and_action.testing import (
	TimeAndActionTestCase,
	make_lot,
	make_master,
	use_company_holidays,
)
from essdee_yrp.time_and_action.update import get_update_data
from essdee_yrp.time_and_action.web import get_lot_time_and_action, get_open_time_and_actions

TIME_AND_ACTION = "SD YRP Time and Action"


class TestTimeAndActionWeb(TimeAndActionTestCase):
	def setUp(self):
		use_company_holidays([], "2025-01-01", "2028-12-31")
		set_window(3650, 3650)
		self.master = make_master(STEPS, DEPENDENCIES)
		self.lot = make_lot()
		self.name = create_time_and_action("SD YRP Lot", self.lot, self.master.name, "2026-11-02")

	def test_lot_filter_returns_only_that_lot(self):
		rows = get_open_time_and_actions(lot=self.lot)
		self.assertEqual([row.name for row in rows], [self.name])
		self.assertEqual(rows[0].against_id, self.lot)

	def test_item_filter(self):
		item = frappe.db.get_value(TIME_AND_ACTION, self.name, "item")
		self.assertIn(self.name, [row.name for row in get_open_time_and_actions(item=item)])
		self.assertEqual(get_open_time_and_actions(lot=self.lot, item="TA-NO-SUCH-ITEM"), [])

	def test_completed_is_left_out(self):
		frappe.db.set_value(TIME_AND_ACTION, self.name, "status", "Completed")
		self.assertEqual(get_open_time_and_actions(lot=self.lot), [])

	def test_lot_context(self):
		context = get_lot_time_and_action(self.lot)
		self.assertEqual((context["time_and_action"], context["can_create"]), (self.name, False))
		self.assertIsNone(context["create_blocked_reason"])
		lot = make_lot()
		context = get_lot_time_and_action(lot)
		self.assertEqual((context["can_create"], context["create_blocked_reason"]), (False, "no_assigned_person"))
		frappe.db.set_value("SD YRP Lot", lot, "assigned_person", "Administrator")
		context = get_lot_time_and_action(lot)
		self.assertEqual((context["time_and_action"], context["can_create"]), (None, True))
		self.assertIsNone(context["create_blocked_reason"])
		self.assertEqual(context["item"], frappe.db.get_value("SD YRP Lot", lot, "item"))

	def test_contexts_hide_the_ta_without_read_permission(self):
		real = frappe.has_permission

		def no_time_and_action(doctype, *args, **kwargs):
			return False if doctype == TIME_AND_ACTION else real(doctype, *args, **kwargs)

		self.assertTrue(get_lot_time_and_action(self.lot)["can_read"])
		with patch("frappe.has_permission", side_effect=no_time_and_action):
			self.assertEqual(get_lot_time_and_action(self.lot), {"can_read": False})
			self.assertEqual(
				get_production_order_time_and_action(submitted_production_order()), {"can_read": False}
			)

	def test_update_data_flags_update_dates_and_lot_detail(self):
		data = get_update_data(self.name)
		self.assertTrue(data["can_update_dates"])
		self.assertTrue(data["can_view_lot_detail"])
		frappe.db.set_value(TIME_AND_ACTION, self.name, "status", "Completed")
		self.assertFalse(get_update_data(self.name)["can_update_dates"])

	def test_progress_and_next_action(self):
		row = get_open_time_and_actions(lot=self.lot)[0]
		doc = frappe.get_doc(TIME_AND_ACTION, self.name)
		first = doc.details[0]
		self.assertEqual((row.dated, row.total), (0, len(doc.details)))
		self.assertEqual((row.next_action, row.next_action_date), (first.action, first.rescheduled_date))
		frappe.db.set_value("SD YRP Time and Action Detail", first.name, "actual_date", first.rescheduled_date)
		row = get_open_time_and_actions(lot=self.lot)[0]
		self.assertEqual((row.dated, row.next_action), (1, doc.details[1].action))

	def test_against_for_lot_and_production_order(self):
		order = submitted_production_order()
		name = create_time_and_action("YRP Production Order", order, self.master.name, "2026-11-02")
		rows = {row.name: row for row in get_open_time_and_actions()}
		self.assertEqual((rows[self.name].against, rows[self.name].against_id), ("SD YRP Lot", self.lot))
		self.assertEqual((rows[name].against, rows[name].against_id), ("YRP Production Order", order))
		self.assertEqual(rows[name].total, len(self.master.details))
