"""Process-cost attribute choices follow the current IPD process input stage."""

import unittest
from inspect import unwrap
from unittest.mock import Mock, patch

import frappe

from essdee_yrp.process_cost import get_item_attributes


class ProcessCostStageTest(unittest.TestCase):
	def test_printing_input_stage_offers_panel_and_colour(self):
		ipd = frappe._dict(
			cutting_process="Cutting",
			stiching_process="Stitching",
			packing_process="Packing",
			stiching_attribute="Panel",
			packing_attribute="Colour",
			primary_item_attribute="Size",
			stiching_in_stage="Cut",
			stiching_out_stage="Piece",
			ipd_processes=[frappe._dict(process_name="Printing", in_stage="Cut", out_stage="Cut")],
		)
		with (
			patch("essdee_yrp.process_cost._resolve_ipd_name", return_value="IPD"),
			patch("essdee_yrp.process_cost._check_process_cost_permissions"),
			patch("essdee_yrp.process_cost.frappe.db", new=frappe._dict(get_value=Mock())) as db,
			patch("essdee_yrp.process_cost.frappe.has_permission"),
			patch("essdee_yrp.process_cost.frappe.get_cached_doc", return_value=ipd),
		):
			db.get_value.return_value = 0
			result = unwrap(get_item_attributes)(
				"Item Attribute",
				"",
				"name",
				0,
				20,
				{"item": "Garment", "lot": "Lot", "process": "Printing"},
			)
		self.assertEqual(result, [["Panel"], ["Colour"]])

	def test_cloth_process_uses_selected_cloth_ipd_attributes(self):
		ipd = frappe._dict(
			is_cloth_item=1, item_attributes=[frappe._dict(attribute="Dia"), frappe._dict(attribute="Colour")]
		)
		with (
			patch("essdee_yrp.process_cost._check_process_cost_permissions"),
			patch("essdee_yrp.process_cost._resolve_ipd_name", return_value="Cloth IPD") as resolve,
			patch("essdee_yrp.process_cost.frappe.has_permission"),
			patch("essdee_yrp.process_cost.frappe.get_cached_doc", return_value=ipd),
		):
			result = unwrap(get_item_attributes)(
				"Item Attribute", "", "name", 0, 20, {"item": "Cloth", "lot": "Lot", "process": "Knitting"}
			)
		resolve.assert_called_once_with("Cloth", "Lot", "Knitting")
		self.assertEqual(result, [["Dia"], ["Colour"]])

	def _resolve(self, item, fabric_ipds, context_options=()):
		from essdee_yrp.process_cost import _resolve_ipd_name

		with (
			patch(
				"essdee_yrp.process_cost.attribute_db.get_value",
				side_effect=lambda doctype, name, field: {"item": "Garment", "production_detail": "Lot IPD"}[
					field
				],
			),
			patch("essdee_yrp.process_cost.frappe.get_all", return_value=list(fabric_ipds)),
			patch(
				"essdee_yrp.api.work_order._get_work_order_selection_context",
				return_value={"options": list(context_options)},
			),
		):
			return _resolve_ipd_name(item, "Lot", "Knitting")

	def test_ipd_resolution_uses_the_lot_ipd_for_the_lot_item(self):
		self.assertEqual(self._resolve("Garment", []), "Lot IPD")

	def test_ipd_resolution_uses_the_lot_fabric_ipd_for_a_cloth_item(self):
		self.assertEqual(self._resolve("Cloth", ["Cloth IPD"]), "Cloth IPD")

	def test_ipd_resolution_returns_none_for_an_unrelated_item(self):
		self.assertIsNone(self._resolve("Other Cloth", []))

	def test_ipd_resolution_narrows_repeated_cloth_by_process(self):
		options = [{"item": "Cloth", "production_detail": "Knit IPD"}]
		self.assertEqual(self._resolve("Cloth", ["Knit IPD", "Dye IPD"], options), "Knit IPD")

	def _save(self, doc, ipd_name=None):
		from essdee_yrp.process_cost import before_validate

		values = {
			("Item", "Cloth", "disabled"): 0,
			("Item", "Cloth", "stock_uom"): "Kg",
			("Item", "Garment", "disabled"): 0,
			("Item", "Garment", "stock_uom"): "Nos",
		}
		with (
			patch("essdee_yrp.process_cost.attribute_db.get_value", return_value="Garment"),
			patch("essdee_yrp.process_cost._resolve_ipd_name", return_value=ipd_name),
			patch("essdee_yrp.process_cost.is_folding_lot", return_value=False),
			patch("essdee_yrp.process_cost.frappe.db.get_value", side_effect=lambda *args: values.get(args)),
		):
			before_validate(doc)
		return doc

	def test_save_keeps_the_chosen_item_for_any_process(self):
		doc = self._save(frappe._dict(lot="Lot", process_name="Printing", item="Cloth"))
		self.assertEqual((doc.item, doc.uom), ("Cloth", "Kg"))

	def test_save_fills_the_lot_item_only_when_item_is_empty(self):
		doc = self._save(frappe._dict(lot="Lot", process_name="Printing", item=None))
		self.assertEqual((doc.item, doc.uom), ("Garment", "Nos"))

	def test_save_rejects_a_disabled_item(self):
		with patch("essdee_yrp.process_cost.frappe.throw", side_effect=frappe.ValidationError):
			with self.assertRaises(frappe.ValidationError):
				self._save(frappe._dict(lot="Lot", process_name="Printing", item="Disabled"))

	def test_save_without_ipd_allows_a_flat_cost(self):
		doc = self._save(
			frappe._dict(lot="Lot", process_name="Printing", item="Cloth", depends_on_attribute=1)
		)
		self.assertEqual(doc.item, "Cloth")

	def test_save_without_ipd_rejects_an_attribute(self):
		with self.assertRaises(frappe.ValidationError) as raised:
			self._save(
				frappe._dict(
					lot="Lot", process_name="Printing", item="Cloth", depends_on_attribute=1, attribute="Size"
				)
			)
		self.assertIn("no Item Production Detail", str(raised.exception))


class ProcessCostDependentAttributeTest(unittest.TestCase):
	"""A Process Cost cannot be priced by the IPD dependent attribute (Stage)."""

	DB_VALUES = {
		("Item", "Garment", "disabled"): 0,
		("Item", "Garment", "stock_uom"): "Nos",
		("YRP Item Production Detail", "IPD", "dependent_attribute"): "Stage",
	}

	def _before_validate(self, doc, ipd_name="IPD", folding=False):
		from essdee_yrp.process_cost import before_validate

		with (
			patch("essdee_yrp.process_cost.is_folding_lot", return_value=folding),
			patch("essdee_yrp.process_cost.attribute_db.get_value", return_value="Garment"),
			patch("essdee_yrp.process_cost._resolve_ipd_name", return_value=ipd_name),
			patch(
				"essdee_yrp.process_cost.frappe.db.get_value",
				side_effect=lambda *args: self.DB_VALUES.get(args),
			),
		):
			before_validate(doc)

	def _doc(self, attribute):
		return frappe._dict(
			lot="Lot", process_name="Printing", item="Garment", depends_on_attribute=1, attribute=attribute
		)

	def test_save_rejects_the_ipd_dependent_attribute(self):
		with self.assertRaises(frappe.ValidationError) as raised:
			self._before_validate(self._doc("Stage"))
		self.assertIn("cannot depend on", str(raised.exception))
		self.assertIn("Stage", str(raised.exception))

	def test_save_accepts_another_attribute(self):
		doc = self._doc("Size")
		self._before_validate(doc)
		self.assertEqual(doc.attribute, "Size")

	def test_folding_lot_without_ipd_accepts_any_attribute(self):
		doc = self._doc("Stage")
		self._before_validate(doc, ipd_name=None, folding=True)
		self.assertEqual(doc.attribute, "Stage")

	def test_folding_lot_with_resolved_ipd_rejects_dependent_attribute(self):
		with self.assertRaises(frappe.ValidationError):
			self._before_validate(self._doc("Stage"), folding=True)

	def test_attribute_picker_hides_the_ipd_dependent_attribute(self):
		ipd = frappe._dict(dependent_attribute="Stage", ipd_processes=[])
		item = frappe._dict(attributes=[frappe._dict(attribute=name) for name in ("Colour", "Stage", "Size")])
		with (
			patch("essdee_yrp.process_cost._check_process_cost_permissions"),
			patch("essdee_yrp.process_cost._resolve_ipd_name", return_value="IPD"),
			patch("essdee_yrp.process_cost.frappe.db.get_value", return_value=1),
			patch("essdee_yrp.process_cost.frappe.has_permission"),
			patch(
				"essdee_yrp.process_cost.frappe.get_cached_doc",
				side_effect=lambda doctype, name: ipd if doctype == "YRP Item Production Detail" else item,
			),
		):
			result = unwrap(get_item_attributes)(
				"Item Attribute", "", "name", 0, 20, {"item": "Garment", "lot": "Lot", "process": "Group"}
			)
		self.assertEqual(result, [["Colour"], ["Size"]])
