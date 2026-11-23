import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from essdee_yrp.finishing.alternative_transfers import get_alternative_quantities
from essdee_yrp.finishing.parsing import json_object
from essdee_yrp.finishing.rebuild import rebuild_finishing_plan


def find_source_plan():
	"""A live source Finishing Plan whose Lot has pieces moved to an alternative Lot."""
	source_lots = frappe.get_all(
		"SD YRP Lot", filters={"is_transferred": 1}, pluck="transferred_lot", order_by="creation desc"
	)
	moved = get_alternative_quantities(source_lots)
	for lot in source_lots:
		plan = frappe.db.get_value("SD YRP Finishing Plan", {"lot": lot}, "name")
		if plan and moved.get(lot):
			return plan, moved[lot]
	return None, None


def transferred_by_row(doc):
	return {
		(row.item_variant, json_object(row.set_combination).get("major_colour")): flt(row.transferred_qty)
		for row in doc.finishing_plan_details
	}


class TestRebuildKeepsAlternativeTransfers(FrappeTestCase):
	def test_rebuild_recomputes_transferred_qty_from_alternative_work_orders(self):
		plan, moved = find_source_plan()
		if not plan:
			self.skipTest("No live Finishing Plan has pieces moved to an alternative Lot")
		doc = frappe.get_doc("SD YRP Finishing Plan", plan)
		for row in doc.finishing_plan_details:
			row.db_set("transferred_qty", 0, update_modified=False)

		rebuild_finishing_plan(plan)

		doc.reload()
		self.assertEqual(sum(flt(row.transferred_qty) for row in doc.finishing_plan_details), moved)
		before = transferred_by_row(doc)
		rebuild_finishing_plan(plan)
		doc.reload()
		self.assertEqual(transferred_by_row(doc), before)
