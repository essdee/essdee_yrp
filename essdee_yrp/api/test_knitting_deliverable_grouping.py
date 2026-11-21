# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, nowdate

from essdee_yrp.api import cloth_program
from essdee_yrp.api.cloth_program import build_cloth_programs
from essdee_yrp.api.test_cloth_program import _ensure_iav, _ensure_item, _ensure_process, _reset_cpd
from essdee_yrp.api.test_work_order import (
	_ensure_address,
	_ensure_attributed_item,
	_ensure_default_received_type,
)
from essdee_yrp.api.work_order import calculate_fabric_deliverables, get_fabric_deliverable_context
from essdee_yrp.fabric_reference import get_reference_allocations

COLOURS = 5
DIAS = 6
PROGRAM_QTY = 73.0


class TestKnittingDeliverableGrouping(IntegrationTestCase):
	"""Manual knitting saves one physical Greige row per Dia with per-colour allocations."""

	def setUp(self):
		suffix = frappe.generate_hash(length=6)
		self.greige = _ensure_iav("Colour", f"_Test KG Greige {suffix}")
		self.colours = [
			_ensure_iav("Colour", f"_Test KG Colour {index} {suffix}") for index in range(COLOURS)
		]
		self.dias = [_ensure_iav("Dia", f"_Test KG {20 + index} Dia {suffix}") for index in range(DIAS)]
		self.yarn = _ensure_item(f"_Test KG Yarn {suffix}")
		self.cloth = _ensure_attributed_item(f"_Test KG Cloth {suffix}", ["Dia", "Colour"])
		frappe.db.set_value("Item", self.cloth, "is_cloth_item", 1)
		_reset_cpd(self.cloth)
		self.knitting = _ensure_process(f"_Test KG Knit {suffix}", is_item_conversion=1)
		self.dyeing = _ensure_process(f"_Test KG Dye {suffix}")
		for process in (self.knitting, self.dyeing):
			frappe.db.set_value("YRP Process", process, "is_cloth_process", 1)
		_ensure_default_received_type()
		self.old_knitting = frappe.db.get_single_value("SD YRP IPD Settings", "default_knitting_process")
		frappe.db.set_single_value("SD YRP IPD Settings", "default_knitting_process", self.knitting)
		frappe.clear_cache(doctype="SD YRP IPD Settings")

		self.lot = frappe.get_doc({"doctype": "SD YRP Lot", "lot_name": f"_Test KG Lot {suffix}"}).insert(
			ignore_permissions=True
		)
		selection = {
			"cloth_item": self.cloth,
			"yarn_item": self.yarn,
			"knitting_process": self.knitting,
			"dyeing_process": self.dyeing,
			"compacting_process": None,
			"cloth_per_kg_yarn": 1.0,
			"greige_colour": self.greige,
		}
		demand = {(self.cloth, dia, colour): PROGRAM_QTY for dia in self.dias for colour in self.colours}
		with patch.object(cloth_program, "compute_cloth_demand", return_value=demand):
			build_cloth_programs(self.lot.name, [selection])
		self.address = _ensure_address(f"_Test KG Supplier {suffix}")

	def tearDown(self):
		frappe.db.set_single_value("SD YRP IPD Settings", "default_knitting_process", self.old_knitting)
		frappe.clear_cache(doctype="SD YRP IPD Settings")

	def make_work_order(self, process):
		return frappe.get_doc(
			{
				"doctype": "YRP Work Order",
				"wo_date": nowdate(),
				"process_name": process,
				"item": self.cloth,
				"lot": self.lot.name,
				"planned_start_date": nowdate(),
				"planned_end_date": nowdate(),
				"supplier_address": self.address,
				"delivery_address": self.address,
			}
		).insert(ignore_permissions=True)

	def get_variant_attributes(self, item_variant):
		return {row.attribute: row.attribute_value for row in frappe.get_doc("Item", item_variant).attributes}

	def test_manual_knitting_routes_save_as_one_greige_row_per_dia(self):
		work_order = self.make_work_order(self.knitting)
		row = get_fabric_deliverable_context(work_order.name)["rows"][0]
		self.assertTrue(row["reference_routed"])
		self.assertTrue(row["manual_io"])
		qty_rows = row["qty_rows"]
		self.assertEqual(len(qty_rows), COLOURS * DIAS)
		self.assertEqual({qty_row["knit_colour"] for qty_row in qty_rows}, {self.greige})
		self.assertTrue(all(flt(qty_row["prefill"]) == PROGRAM_QTY for qty_row in qty_rows))

		# The /web contract sends one line per matrix route with the physical split.
		entries = [
			{
				"key": qty_row["key"],
				"matrix_key": qty_row["key"],
				"colour": qty_row["knit_colour"],
				"qty": qty_row["prefill"],
				"inputs": [{"key": qty_row["knitting_inputs"][0]["key"], "qty": qty_row["prefill"]}],
			}
			for qty_row in qty_rows
		]
		calculate_fabric_deliverables(
			work_order.name, [{"fabric_row": row["fabric_row"], "entries": entries}]
		)
		work_order.reload()

		self.assertEqual(len(work_order.receivables), DIAS)
		for receivable in work_order.receivables:
			attributes = self.get_variant_attributes(receivable.item_variant)
			self.assertEqual(attributes["Colour"], self.greige)
			self.assertEqual(flt(receivable.qty), COLOURS * PROGRAM_QTY)
			allocations = get_reference_allocations(receivable)
			self.assertEqual(len(allocations), COLOURS)
			for reference, qty in allocations.items():
				self.assertEqual(self.get_variant_attributes(reference)["Dia"], attributes["Dia"])
				self.assertEqual(flt(qty), PROGRAM_QTY)
		calculated = [row for row in work_order.deliverables if row.is_calculated]
		self.assertEqual(sum(flt(row.qty) for row in calculated), DIAS * COLOURS * PROGRAM_QTY)

		reopened = get_fabric_deliverable_context(work_order.name)["rows"][0]["qty_rows"]
		self.assertTrue(all(flt(qty_row["prefill"]) == PROGRAM_QTY for qty_row in reopened))
		next_rows = get_fabric_deliverable_context(self.make_work_order(self.knitting).name)["rows"][0][
			"qty_rows"
		]
		for qty_row in next_rows:
			self.assertEqual(flt(qty_row["ordered"]), PROGRAM_QTY)
			self.assertEqual(flt(qty_row["balance"]), 0)

	def test_actual_dia_grn_consumes_the_saved_manual_knitting_contract(self):
		from essdee_yrp.api.work_order import _resolve_variant
		from essdee_yrp.fabric_grn import calculate_consumption_plan

		work_order = self.make_work_order(self.knitting)
		row = get_fabric_deliverable_context(work_order.name)["rows"][0]
		entries = [
			{
				"key": qty_row["key"],
				"matrix_key": qty_row["key"],
				"colour": qty_row["knit_colour"],
				"qty": qty_row["prefill"],
				"inputs": [
					{"key": qty_row["knitting_inputs"][0]["key"], "qty": flt(qty_row["prefill"]) * 1.1}
				],
			}
			for qty_row in row["qty_rows"]
		]
		calculate_fabric_deliverables(
			work_order.name, [{"fabric_row": row["fabric_row"], "entries": entries}]
		)
		work_order.reload()
		self.assertFalse(work_order.cloth_execution_version)
		planned = work_order.receivables[0]
		actual_dia = _ensure_iav("Dia", f"_Test KG Actual Dia {frappe.generate_hash(length=6)}")
		actual_variant = _resolve_variant(self.cloth, {"Dia": actual_dia, "Colour": self.greige})
		grn = frappe._dict(
			against="YRP Work Order",
			against_id=work_order.name,
			flags=frappe._dict(skip_input_stock_check=True),
			items=[
				frappe._dict(
					name="GRNI-ACTUAL-DIA",
					item_variant=actual_variant,
					quantity=flt(planned.qty) / 2,
					ref_docname=planned.name,
				)
			],
		)

		with patch("essdee_yrp.fabric_grn._supplier_stock", return_value=(0, 0)):
			plan = calculate_consumption_plan(grn, work_order)

		yarn_total = sum(flt(deliverable.qty) for deliverable in work_order.deliverables)
		receivable_total = sum(flt(receivable.qty) for receivable in work_order.receivables)
		expected = flt(planned.qty) / 2 * yarn_total / receivable_total
		self.assertEqual({item["received_item_variant"] for item in plan}, {actual_variant})
		self.assertAlmostEqual(sum(flt(item["stock_qty"]) for item in plan), expected, places=3)

	def test_dyeing_popup_keeps_one_row_per_finished_colour(self):
		work_order = self.make_work_order(self.dyeing)
		row = get_fabric_deliverable_context(work_order.name)["rows"][0]
		self.assertFalse(row["reference_routed"])
		qty_rows = row["qty_rows"]
		self.assertEqual(len(qty_rows), COLOURS * DIAS)
		self.assertEqual(
			{qty_row["out_attrs"]["Colour"] for qty_row in qty_rows},
			set(self.colours),
		)
