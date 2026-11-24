"""Recalculate Deliverables on a submitted Work Order."""

from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from essdee_yrp.work_order_recalculate import (
	apply_recalculate_deliverables,
	get_recalculate_deliverables_preview,
	plan_deliverable_recalculation,
)


def _row(name, variant, qty, uom="Nos"):
	return {"name": name, "item_variant": variant, "qty": qty, "uom": uom}


def _expected(variant, qty, uom="Nos"):
	return {"item_variant": variant, "qty": qty, "uom": uom}


class TestPlanDeliverableRecalculation(TestCase):
	def test_unchanged_updated_added_and_removed(self):
		plan = plan_deliverable_recalculation(
			current=[_row("r1", "A", 10), _row("r2", "B", 5), _row("r3", "C", 3)],
			expected=[_expected("A", 10), _expected("B", 8), _expected("D", 4)],
			locked={},
		)
		self.assertEqual([row["item_variant"] for row in plan["unchanged"]], ["A"])
		self.assertEqual(
			[(row["row_name"], row["old_qty"], row["new_qty"]) for row in plan["updated"]],
			[("r2", 5, 8)],
		)
		self.assertEqual([row["row_name"] for row in plan["removed"]], ["r3"])
		self.assertEqual([(row["item_variant"], row["new_qty"]) for row in plan["added"]], [("D", 4)])
		self.assertEqual(plan["kept"], [])

	def test_delivered_variant_is_never_touched(self):
		plan = plan_deliverable_recalculation(
			current=[_row("r1", "A", 10), _row("r2", "B", 5)],
			expected=[_expected("A", 99)],
			locked={"A": "referenced by Delivery Challan DC-1", "B": "already delivered"},
		)
		self.assertEqual([row["row_name"] for row in plan["kept"]], ["r1", "r2"])
		self.assertEqual(plan["kept"][0]["new_qty"], 99)
		self.assertIsNone(plan["kept"][1]["new_qty"])
		self.assertFalse(plan["updated"] or plan["removed"] or plan["added"])

	def test_duplicate_rows_collapse_into_one_and_uom_change_replaces_row(self):
		plan = plan_deliverable_recalculation(
			current=[_row("r1", "A", 4), _row("r2", "A", 6), _row("r3", "B", 2, "Meter")],
			expected=[_expected("A", 12), _expected("B", 2, "Nos")],
			locked={},
		)
		self.assertEqual([row["row_name"] for row in plan["updated"]], ["r1"])
		self.assertEqual(plan["updated"][0]["old_qty"], 10)
		self.assertEqual({row["row_name"] for row in plan["removed"]}, {"r2", "r3"})
		self.assertEqual([(row["item_variant"], row["uom"]) for row in plan["added"]], [("B", "Nos")])

	def test_expected_rows_for_one_variant_are_summed(self):
		plan = plan_deliverable_recalculation(
			current=[],
			expected=[_expected("A", 1.25), _expected("A", 2.5)],
			locked={},
		)
		self.assertEqual([(row["item_variant"], row["new_qty"]) for row in plan["added"]], [("A", 3.75)])


class TestRecalculateDeliverablesOnWorkOrder(IntegrationTestCase):
	"""Exercise a submitted Stitching Work Order with no Delivery Challan."""

	work_order = "YRP-WO-2026-00090"
	label = "Size Label Premium Blended Cotton (Taffeta)-45 cm"
	elastic = "Inner Elastic-30 mm"
	tape = "Hamic - Tiger Bermuda Twilltape 12mm-Biscuit"

	def setUp(self):
		if not frappe.db.exists("YRP Work Order", {"name": self.work_order, "docstatus": 1}):
			self.skipTest(f"Fixture {self.work_order} is unavailable")
		frappe.db.savepoint("recalculate_deliverables_test")
		self.addCleanup(frappe.db.rollback, save_point="recalculate_deliverables_test")

	def _accessories(self):
		doc = frappe.get_doc("YRP Work Order", self.work_order)
		return {
			row.item_variant: row
			for row in doc.deliverables
			if row.get("set_combination") in (None, "", "{}")
		}

	def test_restores_drifted_rows_without_touching_delivered_rows(self):
		before = self._accessories()
		label, elastic, tape = before[self.label], before[self.elastic], before[self.tape]
		frappe.db.set_value(label.doctype, label.name, {"qty": 1, "pending_quantity": 1})
		frappe.db.delete(elastic.doctype, {"name": elastic.name})
		frappe.db.set_value(tape.doctype, tape.name, {"qty": 50, "pending_quantity": 40})
		stale = frappe.get_doc("YRP Work Order", self.work_order).append(
			"deliverables", {**label.as_dict(), "name": None, "idx": 99, "item_variant": "Inner Elastic-8 mm"}
		)
		stale.db_insert()

		preview = get_recalculate_deliverables_preview(self.work_order)
		self.assertEqual([row["row_name"] for row in preview["updated"]], [label.name])
		self.assertEqual([row["item_variant"] for row in preview["added"]], [self.elastic])
		self.assertEqual([row["row_name"] for row in preview["removed"]], [stale.name])
		self.assertEqual([row["row_name"] for row in preview["kept"]], [tape.name])

		result = apply_recalculate_deliverables(self.work_order)
		self.assertTrue(result["has_changes"])

		after = self._accessories()
		self.assertEqual(after[self.label].name, label.name)
		self.assertEqual((flt(after[self.label].qty), flt(after[self.label].pending_quantity)), (56, 56))
		added = after[self.elastic]
		self.assertEqual(
			(flt(added.qty), flt(added.pending_quantity), added.is_calculated), (1070.72, 1070.72, 1)
		)
		self.assertEqual((added.lot, added.uom), (elastic.lot, elastic.uom))
		self.assertTrue(added.received_type)
		self.assertNotIn("Inner Elastic-8 mm", after)
		self.assertEqual((flt(after[self.tape].qty), flt(after[self.tape].pending_quantity)), (50, 40))

		doc = frappe.get_doc("YRP Work Order", self.work_order)
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.status, "Partially Delivered")
		self.assertEqual([row.idx for row in doc.deliverables], list(range(1, len(doc.deliverables) + 1)))
		self.assertFalse(get_recalculate_deliverables_preview(self.work_order)["has_changes"])

	def test_variant_on_a_submitted_delivery_challan_is_kept(self):
		with patch(
			"essdee_yrp.work_order_recalculate.get_delivered_variants",
			return_value={self.label: "DC-TEST"},
		):
			row = self._accessories()[self.label]
			frappe.db.set_value(row.doctype, row.name, "qty", 2)
			preview = get_recalculate_deliverables_preview(self.work_order)
		self.assertEqual([change["row_name"] for change in preview["kept"]], [row.name])
		self.assertIn("DC-TEST", preview["kept"][0]["reason"])
		self.assertFalse(preview["has_changes"])

	def test_no_changes_is_reported_and_leaves_rows_alone(self):
		doc = frappe.get_doc("YRP Work Order", self.work_order)
		before = {row.name: (row.item_variant, row.qty) for row in doc.deliverables}
		self.assertFalse(get_recalculate_deliverables_preview(self.work_order)["has_changes"])
		self.assertFalse(apply_recalculate_deliverables(self.work_order)["has_changes"])
		doc = frappe.get_doc("YRP Work Order", self.work_order)
		self.assertEqual(before, {row.name: (row.item_variant, row.qty) for row in doc.deliverables})


class TestRecalculateMatchesChangeItemAndCalculateItems(IntegrationTestCase):
	"""Both submitted-WO actions must expect what ``Calculate Items`` builds today."""

	work_order = "YRP-WO-2026-00070"

	def setUp(self):
		if not frappe.db.exists("YRP Work Order", {"name": self.work_order, "docstatus": 1}):
			self.skipTest(f"Fixture {self.work_order} is unavailable")

	def test_expected_accessories_are_shared(self):
		from essdee_yrp.garment_work_order import _processes, calculate_garment_process_rows
		from essdee_yrp.work_order_actions import _work_order_demands
		from essdee_yrp.work_order_change_item import get_expected_accessory_rows

		doc = frappe.get_doc("YRP Work Order", self.work_order)
		ipd = frappe.get_cached_doc("YRP Item Production Detail", doc.production_detail)
		plan = get_recalculate_deliverables_preview(self.work_order)
		recalculated = {
			row["item_variant"]: (row["new_qty"], row["uom"])
			for key in ("added", "updated", "unchanged", "kept")
			for row in plan[key]
			if row["new_qty"] is not None
		}
		change_item = {
			row["item_variant"]: (flt(row["qty"], 3), row["uom"])
			for row in get_expected_accessory_rows(doc, ipd)
		}
		self.assertTrue(change_item)
		for variant, value in change_item.items():
			self.assertEqual(recalculated.get(variant), value, variant)

		lot = frappe.get_doc("SD YRP Lot", doc.lot)
		deliverables, _receivables = calculate_garment_process_rows(
			ipd, lot, doc.process_name, _work_order_demands(doc)
		)
		created = {row["item_variant"]: (flt(row["qty"], 3), row.get("uom")) for row in deliverables}
		for variant, value in change_item.items():
			self.assertEqual(created.get(variant), value, variant)
		self.assertEqual(_processes(doc.process_name), ["Stitching"])
