from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.fabric_store.documents.goods_received_note import preview_goods_received_note_source
from essdee_yrp.overrides.goods_received_note import (
	validate_quality_inspection_passed,
	validate_work_order_has_passed_inspection,
)
from essdee_yrp.sewing.plan import is_sewing_work_order

MODULE = "essdee_yrp.overrides.goods_received_note"
IPD = frappe._dict(
	is_set_item=0,
	packing_attribute="Colour",
	primary_item_attribute="Size",
	set_item_attribute=None,
	major_attribute_value=None,
)


class TestGrnQualityInspection(TestCase):
	def grn(self, **values):
		grn = frappe._dict(
			against="YRP Work Order",
			against_id="WO-1",
			is_return=0,
			lot="LOT-1",
			items=[
				frappe._dict(
					item_variant="TEE-Red-M", quantity=10, set_combination='{"major_colour": "Red"}'
				),
				frappe._dict(item_variant="LABEL", quantity=10, set_combination="{}"),
			],
		)
		grn.update(values)
		return grn

	def validate(self, grn, inspected, is_sewing=True):
		attributes = {"TEE-Red-M": {"Colour": "Red", "Size": "M"}, "LABEL": {}}
		work_order = frappe._dict(process_name="Stitching", is_rework=0, production_detail="IPD-1")
		with (
			patch(f"{MODULE}.is_sewing_work_order", return_value=is_sewing),
			patch(f"{MODULE}.frappe.db.sql", return_value=inspected) as sql,
			patch(f"{MODULE}.frappe.db.get_value", side_effect=[work_order, IPD]),
			patch(f"{MODULE}.get_variant_attr_details", side_effect=attributes.get),
		):
			validate_quality_inspection_passed(grn)
		return sql

	def test_submitted_pass_inspection_for_the_colour_and_size_allows_the_grn(self):
		sql = self.validate(self.grn(), [frappe._dict(colour="Red", size="M")])

		self.assertIn("inspection.result = 'Pass'", sql.call_args.args[0])
		self.assertIn("inspection.docstatus = 1", sql.call_args.args[0])

	def test_missing_fail_or_hold_inspection_blocks_the_grn(self):
		with self.assertRaises(frappe.ValidationError) as raised:
			self.validate(self.grn(), [frappe._dict(colour="Red", size="L")])

		self.assertIn("Red / M", str(raised.exception))
		self.assertIn("result Pass", str(raised.exception))

	def test_inspection_is_looked_up_for_the_grn_work_order_only(self):
		sql = self.validate(self.grn(against_id="WO-2"), [frappe._dict(colour="Red", size="M")])

		self.assertIn("inspection.against_id = %(work_order)s", sql.call_args.args[0])
		self.assertEqual(sql.call_args.args[1], {"work_order": "WO-2"})

	def test_returns_and_non_sewing_work_orders_are_exempt(self):
		self.assertFalse(self.validate(self.grn(is_return=1), []).called)
		self.assertFalse(self.validate(self.grn(), [], is_sewing=False).called)

	def test_sewing_work_order_without_a_sewing_plan_still_needs_an_inspection(self):
		with (
			patch(f"{MODULE}.frappe.db.exists", return_value=False),
			self.assertRaises(frappe.ValidationError) as raised,
		):
			self.validate(self.grn(), [])

		self.assertIn("Red / M", str(raised.exception))

	def test_colour_falls_back_to_the_variant_when_the_row_has_no_major_colour(self):
		grn = self.grn()
		grn["items"][0].set_combination = "{}"
		with self.assertRaises(frappe.ValidationError) as raised:
			self.validate(grn, [])

		self.assertIn("Red / M", str(raised.exception))


class TestSewingWorkOrderForInspection(TestCase):
	def is_sewing(self, work_order, is_group=0, has_child=False):
		with patch("frappe.db", Mock()) as db:
			db.get_single_value.return_value = "Stitching"
			db.get_value.return_value = is_group
			db.exists.return_value = has_child
			return is_sewing_work_order(frappe._dict(work_order))

	def test_stitching_and_groups_containing_stitching_are_sewing(self):
		self.assertTrue(self.is_sewing({"process_name": "Stitching"}))
		self.assertTrue(self.is_sewing({"process_name": "Group"}, is_group=1, has_child=True))

	def test_other_processes_and_rework_are_not_sewing(self):
		self.assertFalse(self.is_sewing({"process_name": "Dyeing"}))
		self.assertFalse(self.is_sewing({"process_name": "Group"}, is_group=1, has_child=False))
		self.assertFalse(self.is_sewing({"process_name": "Stitching", "is_rework": 1}))


class TestWebGrnSourceNeedsInspection(TestCase):
	def validate(self, inspected, is_sewing=True):
		with (
			patch(f"{MODULE}.frappe.db.get_value", return_value=frappe._dict(process_name="Stitching")),
			patch(f"{MODULE}.is_sewing_work_order", return_value=is_sewing),
			patch(f"{MODULE}.frappe.db.sql", return_value=inspected) as sql,
		):
			validate_work_order_has_passed_inspection("WO-2")
		return sql

	def test_sewing_work_order_without_a_passed_inspection_is_rejected(self):
		with self.assertRaises(frappe.ValidationError) as raised:
			self.validate([])

		self.assertIn("WO-2", str(raised.exception))

	def test_inspected_or_non_sewing_work_orders_are_allowed(self):
		self.validate([frappe._dict(colour="Red", size="M")])
		self.assertFalse(self.validate([], is_sewing=False).called)

	def test_web_preview_checks_the_selected_work_order_before_building_the_editor(self):
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
			patch(
				"essdee_yrp.fabric_store.documents.goods_received_note.validate_work_order_has_passed_inspection",
				side_effect=frappe.ValidationError("no inspection"),
			) as check,
			patch("essdee_yrp.fabric_store.documents.goods_received_note._source_defaults") as defaults,
			self.assertRaises(frappe.ValidationError),
		):
			preview_goods_received_note_source({"against": "YRP Work Order", "against_id": "WO-2"})
		check.assert_called_once_with("WO-2")
		defaults.assert_not_called()


class TestGrnQualityInspectionOnSiteData(IntegrationTestCase):
	def test_sewing_work_order_without_sewing_plan_or_inspection_cannot_receive(self):
		"""Regression: an external Stitching WO (no Sewing Plan) received a GRN with no inspection of its own."""
		name = frappe.db.sql(
			"""
				select grn.name
				from `tabYRP Goods Received Note` grn
				join `tabYRP Work Order` wo on wo.name = grn.against_id
				where grn.against = 'YRP Work Order' and grn.is_return = 0 and grn.docstatus = 1
				  and wo.process_name = 'Stitching' and wo.is_rework = 0
				  and not exists (select 1 from `tabSD YRP Sewing Plan` plan where plan.work_order = wo.name)
				  and not exists (
					select 1 from `tabSD YRP Essdee Quality Inspection` inspection
					where inspection.against_id = wo.name and inspection.docstatus = 1 and inspection.result = 'Pass'
				  )
				order by grn.creation desc
				limit 1
			""",
			pluck=True,
		)
		if not name:
			self.skipTest("Requires a received Stitching Work Order without an inspection")
		grn = frappe.get_doc("YRP Goods Received Note", name[0])

		with self.assertRaises(frappe.ValidationError) as raised:
			validate_quality_inspection_passed(grn)

		self.assertIn(grn.against_id, str(raised.exception))
