"""Change Item on a submitted Work Order."""

from unittest import TestCase

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from essdee_yrp.work_order_change_item import (
	apply_bom_accessory_changes,
	get_wo_bom_accessory_change_preview,
	get_wo_bom_accessory_items,
	plan_item_changes,
)


def _current(row_name, variant, template, attrs, qty=10, uom="Nos", eligible=True, reason=None):
	return {
		"row_name": row_name,
		"item_variant": variant,
		"template": template,
		"attrs": attrs,
		"qty": qty,
		"uom": uom,
		"eligible": eligible,
		"reason": reason,
	}


def _expected(variant, template, attrs, qty=12, uom="Nos"):
	return {"item_variant": variant, "template": template, "attrs": attrs, "qty": qty, "uom": uom}


def _summary(changes):
	return [(change["row_name"], change["action"], change["new_variant"]) for change in changes]


class TestPlanItemChanges(TestCase):
	def test_single_variant_swap_keeps_quantity(self):
		changes = plan_item_changes(
			current=[_current("r1", "Button-Red", "Button", {"Colour": "Red"}, qty=10)],
			expected=[_expected("Button-Blue", "Button", {"Colour": "Blue"}, qty=12)],
			selected={"Button": "bom1"},
		)
		self.assertEqual(_summary(changes), [("r1", "replace", "Button-Blue")])
		self.assertEqual((changes[0]["new_qty"], changes[0]["calculated_qty"]), (10, 12))
		self.assertEqual(changes[0]["selection_id"], "bom1")
		self.assertTrue(changes[0]["eligible"])

	def test_exact_variant_is_unchanged(self):
		changes = plan_item_changes(
			current=[_current("r1", "Button-Red", "Button", {"Colour": "Red"})],
			expected=[_expected("Button-Red", "Button", {"Colour": "Red"})],
			selected={"Button": "bom1"},
		)
		self.assertEqual(_summary(changes), [("r1", "unchanged", "Button-Red")])
		self.assertFalse(changes[0]["eligible"])

	def test_replaced_template_rows_pair_by_attributes(self):
		changes = plan_item_changes(
			current=[
				_current("r1", "Label-45", "Label", {"Size": "45"}),
				_current("r2", "Label-50", "Label", {"Size": "50"}),
				_current("r3", "Elastic-30", "Elastic", {"Size": "30"}),
			],
			expected=[
				_expected("Taffeta-50", "Taffeta", {"Size": "50"}),
				_expected("Taffeta-45", "Taffeta", {"Size": "45"}),
				_expected("Elastic-30", "Elastic", {"Size": "30"}),
			],
			selected={"Taffeta": "bom1"},
		)
		self.assertEqual(
			sorted(_summary(changes)), [("r1", "replace", "Taffeta-45"), ("r2", "replace", "Taffeta-50")]
		)

	def test_single_stale_row_pairs_with_single_new_variant(self):
		changes = plan_item_changes(
			current=[_current("r1", "Old Tape-10mm", "Old Tape", {"Width": "10mm"})],
			expected=[_expected("New Tape", "New Tape", {})],
			selected={"New Tape": "bom1"},
		)
		self.assertEqual(_summary(changes), [("r1", "replace", "New Tape")])

	def test_stale_rows_claimed_by_two_selected_rows_are_blocked(self):
		changes = plan_item_changes(
			current=[_current("r1", "Label-45", "Label", {"Size": "45"})],
			expected=[
				_expected("Taffeta-45", "Taffeta", {"Size": "45"}),
				_expected("Satin-45", "Satin", {"Size": "45"}),
			],
			selected={"Taffeta": "bom1", "Satin": "bom2"},
		)
		self.assertEqual({change["action"] for change in changes}, {"blocked"})
		self.assertIn("more than one", changes[0]["reason"])

	def test_new_variant_without_existing_row_is_blocked(self):
		changes = plan_item_changes(
			current=[],
			expected=[_expected("Elastic-30", "Elastic", {"Size": "30"})],
			selected={"Elastic": "bom1"},
		)
		self.assertEqual(_summary(changes), [("bom1", "blocked", "Elastic-30")])
		self.assertEqual(changes[0]["reason"], "No existing Work Order row was found.")

	def test_delivered_row_is_blocked(self):
		changes = plan_item_changes(
			current=[
				_current("r1", "Button-Red", "Button", {"Colour": "Red"}, eligible=False, reason="delivered")
			],
			expected=[_expected("Button-Blue", "Button", {"Colour": "Blue"})],
			selected={"Button": "bom1"},
		)
		self.assertEqual(_summary(changes), [("r1", "blocked", "Button-Blue")])
		self.assertEqual(changes[0]["reason"], "delivered")

	def test_unit_change_takes_recalculated_qty_and_unit(self):
		changes = plan_item_changes(
			current=[_current("r1", "Bag-4.5 x 6", "Bag", {}, qty=2440, uom="Nos")],
			expected=[_expected("Poly Bag-5.5 x 7", "Poly Bag", {}, qty=0.488, uom="Kg")],
			selected={"Poly Bag": "bom1"},
		)
		self.assertEqual(_summary(changes), [("r1", "replace", "Poly Bag-5.5 x 7")])
		self.assertEqual((changes[0]["new_qty"], changes[0]["new_uom"]), (0.488, "Kg"))
		self.assertTrue(changes[0]["qty_recalculated"])
		self.assertEqual(changes[0]["note"], "qty recalculated (unit Nos → Kg)")

	def test_delivered_row_with_unit_change_stays_blocked(self):
		changes = plan_item_changes(
			current=[
				_current(
					"r1", "Tape-A", "Tape", {"Colour": "A"}, uom="Meter", eligible=False, reason="delivered"
				)
			],
			expected=[_expected("Tape-B", "Tape", {"Colour": "B"}, uom="Nos")],
			selected={"Tape": "bom1"},
		)
		self.assertEqual((changes[0]["action"], changes[0]["reason"]), ("blocked", "delivered"))

	def test_many_variants_of_same_item_are_ambiguous(self):
		changes = plan_item_changes(
			current=[
				_current("r1", "Button-Red", "Button", {"Colour": "Red"}),
				_current("r2", "Button-Green", "Button", {"Colour": "Green"}),
			],
			expected=[
				_expected("Button-Blue", "Button", {"Colour": "Blue"}),
				_expected("Button-White", "Button", {"Colour": "White"}),
			],
			selected={"Button": "bom1"},
		)
		self.assertEqual({change["action"] for change in changes}, {"blocked"})
		self.assertEqual({change["row_name"] for change in changes}, {"r1", "r2"})


class TestChangeItemOnWorkOrder(IntegrationTestCase):
	"""Stitching Work Order whose IPD swapped Size Label 100% Cotton for the Taffeta label."""

	work_order = "YRP-WO-2026-00070"
	old_template = "Size Label 100% Cotton"
	new_template = "Size Label 100%Cotton (Taffeta)"

	def setUp(self):
		if not frappe.db.exists(
			"YRP Work Order", {"name": self.work_order, "docstatus": 1, "open_status": "Open"}
		):
			self.skipTest(f"Fixture {self.work_order} is unavailable")
		self.bom_row = self._bom_row_name()
		for row in self._label_rows():
			size = row.item_variant.rsplit("-", 1)[1]
			frappe.db.set_value(row.doctype, row.name, "item_variant", f"{self.old_template}-{size}")

	def _bom_row_name(self):
		doc = frappe.get_doc("YRP Work Order", self.work_order)
		ipd = frappe.get_doc("YRP Item Production Detail", doc.production_detail)
		return next(row.name for row in ipd.item_bom if row.item == self.new_template)

	def _label_rows(self):
		doc = frappe.get_doc("YRP Work Order", self.work_order)
		return [row for row in doc.deliverables if row.item_variant.startswith("Size Label 100%")]

	def test_lists_item_bom_rows_of_the_work_order_process(self):
		result = get_wo_bom_accessory_items(self.work_order)
		self.assertTrue(result["supported"])
		self.assertIn(self.bom_row, [row["row_name"] for row in result["items"]])

	def test_replaces_old_label_variants_size_by_size(self):
		before = {row.name: (row.item_variant, flt(row.qty)) for row in self._label_rows()}
		preview = get_wo_bom_accessory_change_preview(self.work_order, [self.bom_row])
		ready = [change for change in preview["changes"] if change["action"] == "replace"]
		self.assertEqual(len(ready), len(before))

		result = apply_bom_accessory_changes(self.work_order, [self.bom_row])
		self.assertEqual(len(result["applied"]), len(before))
		after = {row.name: (row.item_variant, flt(row.qty)) for row in self._label_rows()}
		for name, (variant, qty) in before.items():
			size = variant.rsplit("-", 1)[1]
			self.assertEqual(after[name], (f"{self.new_template}-{size}", qty))
		self.assertFalse(
			[
				c
				for c in get_wo_bom_accessory_change_preview(self.work_order, [self.bom_row])["changes"]
				if c["action"] == "replace"
			]
		)

	def test_unit_change_replaces_qty_and_unit_from_recalculation(self):
		doc = frappe.get_doc("YRP Work Order", self.work_order)
		bag = next(row for row in doc.deliverables if row.item_variant.startswith("Plain Poly Bag"))
		frappe.db.set_value(
			bag.doctype,
			bag.name,
			{
				"item_variant": "Plain Poly Bag-Small-4.5 x 6",
				"qty": 2440,
				"pending_quantity": 2440,
				"uom": "Nos",
			},
		)
		ipd = frappe.get_doc("YRP Item Production Detail", doc.production_detail)
		bom_row = next(row.name for row in ipd.item_bom if row.item == "Plain Poly Bag Small")

		change = get_wo_bom_accessory_change_preview(self.work_order, [bom_row])["changes"][0]
		self.assertEqual((change["action"], change["new_uom"]), ("replace", "Kg"))
		self.assertEqual(change["new_qty"], change["calculated_qty"])

		apply_bom_accessory_changes(self.work_order, [bom_row])
		stored = frappe.db.get_value(
			bag.doctype, bag.name, ["item_variant", "qty", "pending_quantity", "uom"], as_dict=True
		)
		self.assertEqual(stored.item_variant, change["new_variant"])
		self.assertEqual(
			(flt(stored.qty, 3), flt(stored.pending_quantity, 3), stored.uom),
			(change["new_qty"], change["new_qty"], "Kg"),
		)
