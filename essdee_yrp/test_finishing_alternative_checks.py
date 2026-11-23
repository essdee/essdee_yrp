import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.finishing.alternative import create_alternative_fp
from essdee_yrp.finishing.alternative_checks import get_configured_lot_problems, throw_alternative_plan_issues

ALTERNATIVE_ITEM = "Casual Designer Vest - 4"
PRODUCTION_DETAIL = "Casual Designer Vest - 4-18"
LOT_NAME = "E2E-ALT-CHECKS"


def find_plan_with_rows():
	"""Latest live plan of another item whose Lot has a Production Order and colour/size rows."""
	for name in frappe.get_all(
		"SD YRP Finishing Plan",
		filters={"item": ["!=", ALTERNATIVE_ITEM]},
		pluck="name",
		order_by="creation desc",
		limit=20,
	):
		plan = frappe.get_doc("SD YRP Finishing Plan", name)
		if not frappe.db.get_value("SD YRP Lot", plan.lot, "production_order"):
			continue
		data = plan.get_finishing_plans()["finishing_qty"]["data"]
		if data:
			return plan, data
	return None, None


class TestAlternativePlanChecks(FrappeTestCase):
	def test_issues_are_raised_as_one_bulleted_message(self):
		with self.assertRaises(frappe.ValidationError) as raised:
			throw_alternative_plan_issues(["First problem", "Second problem"])
		self.assertEqual(
			str(raised.exception),
			"The Alternative Plan cannot be created yet. Fix the following:"
			"<br>• First problem<br>• Second problem",
		)
		throw_alternative_plan_issues([])

	def test_folding_lot_cannot_become_an_alternative_lot(self):
		lot = frappe.new_doc("SD YRP Lot")
		lot.is_folding_lot = 1
		self.assertEqual(get_configured_lot_problems(lot), ["Folding Lot"])

	def test_every_missing_prerequisite_is_listed_in_one_error(self):
		"""An E2E plan whose alternative lacks several prerequisites reports all of them at once."""
		if not frappe.db.exists("YRP Item Production Detail", PRODUCTION_DETAIL):
			self.skipTest("Alternative Item Production Detail is unavailable")
		plan, data = find_plan_with_rows()
		if not plan:
			self.skipTest("No live Finishing Plan has rows")
		colour = next(iter(data))
		size = next(iter(data[colour]["values"]))
		available = data[colour]["values"][size]["balance"]
		converting = max(available, 0) + 5
		quantities = {
			colour: {"check_value": 1, "values": {size: {"conversion_qty": converting}}},
			"Cool Grey": {"check_value": 1, "values": {size: {"conversion_qty": 1}}},
		}
		frappe.clear_messages()

		with self.assertRaises(frappe.ValidationError) as raised:
			create_alternative_fp(
				doc_name=plan.name,
				alternative_item=ALTERNATIVE_ITEM,
				production_detail=PRODUCTION_DETAIL,
				lot_name=LOT_NAME,
				qty_details={"data": {"data": quantities}},
			)

		message = str(raised.exception)
		for expected in (
			f"• {colour} / {size}: converting {converting:g}, but only {available:g} is available",
			f"• Colour Cool Grey is not in Item Production Detail {PRODUCTION_DETAIL}",
			f"• Item {ALTERNATIVE_ITEM} is not configured as an alternative of {plan.item}",
		):
			self.assertIn(expected, message)
		self.assertEqual(len([row for row in frappe.message_log if row]), 1)
		self.assertFalse(frappe.db.exists("SD YRP Lot", {"lot_name": LOT_NAME}))
