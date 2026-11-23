import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from yrp.utils import get_variant_attr_details

from essdee_yrp.finishing import web_entries
from essdee_yrp.finishing.alternative_checks import get_alternative_plan_issues

SOURCE_ITEM = "AISHWARYA PLAIN"
ALTERNATIVE_ITEM = "AISHWARYA PLAIN (S/Box)"
PRODUCTION_DETAIL = "AISHWARYA PLAIN (S/Box)-4"


def find_plan_with_balance():
	"""Latest live plan of SOURCE_ITEM with convertible balance: (plan, balance matrix, {(colour, size): qty})."""
	for name in frappe.get_all(
		"SD YRP Finishing Plan", filters={"item": SOURCE_ITEM}, pluck="name", order_by="creation desc"
	):
		plan = frappe.get_doc("SD YRP Finishing Plan", name)
		data = plan.get_finishing_plans()["finishing_qty"]["data"]
		entered = {
			(colour, size): values["balance"]
			for colour, row in data.items()
			for size, values in row["values"].items()
			if values["balance"] >= 1
		}
		entered = dict(list(entered.items())[:3])
		conversions = [
			{"colour": colour, "size": size, "qty": qty} for (colour, size), qty in entered.items()
		]
		if entered and not get_alternative_plan_issues(
			plan, ALTERNATIVE_ITEM, PRODUCTION_DETAIL, conversions
		):
			return plan, data, entered
	return None, None, None


def quantity_matrix(data, entries):
	matrix = {
		colour: {"checked": False, "sizes": dict.fromkeys(row["values"], 0)} for colour, row in data.items()
	}
	for (colour, size), qty in entries.items():
		matrix[colour]["checked"] = True
		matrix[colour]["sizes"][size] = qty
	return json.dumps(matrix)


def colour_size(variant):
	attributes = get_variant_attr_details(variant)
	return attributes.get("Colour"), attributes.get("Size")


class TestAlternativeLotQuantities(FrappeTestCase):
	def test_calculate_order_keeps_each_rows_cut_qty(self):
		lot = frappe.new_doc("SD YRP Lot")
		for variant, cut_qty in (("V-1", 10), ("V-2", 20)):
			lot.append(
				"lot_order_details",
				{"item_variant": variant, "set_combination": '{"major_colour": "A"}', "cut_qty": cut_qty},
			)
		rebuilt = [
			{"item_variant": variant, "quantity": 5, "set_combination": {"major_colour": "A"}}
			for variant in ("V-1", "V-2")
		]
		with patch(
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.calculate_order_details",
			return_value=(rebuilt, 10),
		):
			lot.calculate_order()
		self.assertEqual([row.cut_qty for row in lot.lot_order_details], [10, 20])

	def test_new_lot_keeps_entered_colour_size_quantities(self):
		if not frappe.db.exists("YRP Item Production Detail", PRODUCTION_DETAIL):
			self.skipTest("Alternative Item Production Detail is unavailable")
		plan, data, entered = find_plan_with_balance()
		if not plan:
			self.skipTest("No live Finishing Plan has a convertible balance")
		values = {
			"alternative_item": ALTERNATIVE_ITEM,
			"production_detail": PRODUCTION_DETAIL,
			"quantities": quantity_matrix(data, entered),
			"lot_source": "New Lot",
			"lot_name": "TEST-ALT-QTY",
		}
		with patch.object(frappe, "enqueue"), patch.object(frappe.db, "commit"):
			result = web_entries.create_alternative_plan(plan, values)
		work_order = frappe.get_doc("YRP Work Order", result["name"])
		lot = frappe.get_doc("SD YRP Lot", work_order.lot)
		expected = {key: (qty, qty) for key, qty in entered.items()}
		self.assertEqual(
			{colour_size(row.item_variant): (row.quantity, row.cut_qty) for row in lot.lot_order_details},
			expected,
		)
		deliverables = {
			colour_size(row.item_variant): row.qty for row in work_order.deliverables if row.uom == "Pieces"
		}
		self.assertEqual(deliverables, entered)
