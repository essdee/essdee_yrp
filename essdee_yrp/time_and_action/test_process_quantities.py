import json

import frappe

from essdee_yrp.time_and_action.create import create_time_and_action
from essdee_yrp.time_and_action.process_quantities import build_quantities, get_action_process_quantities
from essdee_yrp.time_and_action.test_auto_date import cut, made
from essdee_yrp.time_and_action.test_create import submitted_production_order
from essdee_yrp.time_and_action.test_rules import DEPENDENCIES, STEPS, set_window
from essdee_yrp.time_and_action.testing import (
	TimeAndActionTestCase,
	make_lot,
	make_master,
	use_company_holidays,
)
from essdee_yrp.time_and_action.update import get_update_data
from essdee_yrp.time_and_action.work_order_dates import get_item_quantities

START = "2026-11-02"


def quantity(variant, cut_qty, delivered, received):
	return {"item_variant": variant, "cut": cut_qty, "delivered": delivered, "received": received}


def identity(row):
	colour, size = row["item_variant"].split("-")
	return colour, "", size


class TestBuildQuantities(TimeAndActionTestCase):
	def test_rows_follow_size_order_and_skip_empty_items(self):
		items = [
			quantity("RED-L", 50, 50, 40),
			quantity("RED-M", 100, 100, 95),
			quantity("BLUE-M", 0, 0, 0),
			quantity("RED-XL", 0, 5, 0),
		]
		result = build_quantities(items, identity, ["M", "L"])
		self.assertEqual(result["sizes"], ["M", "L", "XL"])
		self.assertEqual(
			[(row["colour"], row["size"]) for row in result["rows"]],
			[("RED", "M"), ("RED", "L"), ("RED", "XL")],
		)
		self.assertEqual(result["rows"][0]["received_percent"], 95)
		self.assertIsNone(result["rows"][2]["delivered_percent"])
		self.assertEqual(
			result["totals"],
			{
				"cut": 150,
				"delivered": 155,
				"received": 135,
				"delivered_percent": 103.3,
				"received_percent": 90,
			},
		)

	def test_same_identity_is_summed(self):
		result = build_quantities([quantity("RED-M", 10, 5, 5), quantity("RED-M", 20, 5, 0)], identity, ["M"])
		self.assertEqual(len(result["rows"]), 1)
		self.assertEqual(result["rows"][0]["cut"], 30)

	def test_empty(self):
		self.assertEqual(
			build_quantities([], identity, []),
			{
				"sizes": [],
				"rows": [],
				"totals": {
					"cut": 0,
					"delivered": 0,
					"received": 0,
					"delivered_percent": None,
					"received_percent": None,
				},
			},
		)

	def test_item_quantities_join_cut_and_work_orders_by_set_combination(self):
		top = {"set_part": "Top", "major_colour": "Red"}
		quantities = get_item_quantities(
			[cut("RED-M", 100, json.dumps(top))],
			[made("RED-M", 60, 50, top), made("RED-M", 40, 30, json.dumps(dict(reversed(top.items()))))],
		)
		self.assertEqual(len(quantities), 1)
		row = next(iter(quantities.values()))
		self.assertEqual((row["cut"], row["delivered"], row["received"]), (100, 100, 80))


class TestActionProcessQuantities(TimeAndActionTestCase):
	def setUp(self):
		use_company_holidays([], "2025-01-01", "2028-12-31")
		set_window(3650, 3650)
		self.master = make_master(STEPS, DEPENDENCIES)
		frappe.db.set_value("SD YRP Action", "TA-TEST-CUT", "process_name", "Cutting")
		frappe.db.set_value("SD YRP Action", "TA-TEST-YARN", "process_name", None)

	def test_lot_action_with_process_returns_lot_state(self):
		lot = make_lot()
		name = create_time_and_action("SD YRP Lot", lot, self.master.name, START)
		result = get_action_process_quantities(name, "TA-TEST-CUT")
		self.assertEqual((result["lot"], result["process_name"], result["rows"]), (lot, "Cutting", []))

	def test_action_without_process_and_order_time_and_action_are_empty(self):
		name = create_time_and_action("SD YRP Lot", make_lot(), self.master.name, START)
		self.assertIsNone(get_action_process_quantities(name, "TA-TEST-YARN")["lot"])
		order = create_time_and_action(
			"YRP Production Order", submitted_production_order(), self.master.name, START
		)
		result = get_action_process_quantities(order, "TA-TEST-CUT")
		self.assertEqual((result["lot"], result["rows"], result["totals"]["cut"]), (None, [], 0))

	def test_unknown_action_and_no_permission_throw(self):
		name = create_time_and_action("SD YRP Lot", make_lot(), self.master.name, START)
		self.assertRaises(frappe.DoesNotExistError, get_action_process_quantities, name, "NOT-AN-ACTION")
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, get_action_process_quantities, name, "TA-TEST-CUT")

	def test_update_data_rows_carry_process_name(self):
		name = create_time_and_action("SD YRP Lot", make_lot(), self.master.name, START)
		processes = {row["action"]: row["process_name"] for row in get_update_data(name)["rows"]}
		self.assertEqual((processes["TA-TEST-CUT"], processes["TA-TEST-YARN"]), ("Cutting", None))
