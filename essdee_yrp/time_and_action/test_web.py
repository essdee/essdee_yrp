import frappe

from essdee_yrp.time_and_action.create import create_time_and_action
from essdee_yrp.time_and_action.test_rules import DEPENDENCIES, STEPS, set_window
from essdee_yrp.time_and_action.testing import (
	TimeAndActionTestCase,
	make_lot,
	make_master,
	use_company_holidays,
)
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
		lot = make_lot()
		self.assertFalse(get_lot_time_and_action(lot)["can_create"])
		frappe.db.set_value("SD YRP Lot", lot, "assigned_person", "Administrator")
		context = get_lot_time_and_action(lot)
		self.assertEqual((context["time_and_action"], context["can_create"]), (None, True))
		self.assertEqual(context["item"], frappe.db.get_value("SD YRP Lot", lot, "item"))
