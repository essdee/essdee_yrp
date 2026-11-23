from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from yrp.yrp.doctype.yrp_work_order.yrp_work_order import get_variant_attributes

from essdee_yrp.hooks import override_doctype_class
from essdee_yrp.overrides.work_order import EssdeeWorkOrder


class TestEssdeeWorkOrderProcessCost(FrappeTestCase):
	def test_work_order_controller_is_overridden(self):
		self.assertEqual(
			override_doctype_class["YRP Work Order"],
			"essdee_yrp.overrides.work_order.EssdeeWorkOrder",
		)

	def test_garment_rate_is_equal_per_panel_type_and_divided_by_panel_count(self):
		work_order = _work_order()
		process_cost = frappe._dict(
			name="TEST-PROCESS-COST",
			depends_on_attribute=1,
			attribute="Colour",
		)
		ipd = frappe._dict(
			stiching_attribute="Panel",
			packing_attribute="Colour",
			primary_item_attribute="Size",
			dependent_attribute="Stage",
		)
		attributes = {
			"GARMENT-BLACK-M": {"Stage": "Piece", "Colour": "Black", "Size": "M"},
			"FRONT-BLACK-M": {
				"Stage": "Cut",
				"Panel": "Front",
				"Colour": "Black",
				"Size": "M",
			},
			"BACK-BLACK-M": {
				"Stage": "Cut",
				"Panel": "Back",
				"Colour": "Black",
				"Size": "M",
			},
			"SLEEVE-BLACK-M": {
				"Stage": "Cut",
				"Panel": "Sleeve",
				"Colour": "Black",
				"Size": "M",
			},
		}

		with (
			patch(
				"essdee_yrp.overrides.work_order.frappe.get_cached_doc",
				return_value=ipd,
			),
			patch(
				"essdee_yrp.overrides.work_order.get_variant_attributes",
				side_effect=lambda item_variant: attributes[item_variant],
			),
			patch(
				"essdee_yrp.overrides.work_order.get_process_cost_rate",
				return_value=3,
			),
		):
			work_order.apply_receivable_process_costs(process_cost)

		by_item = {row.item_variant: row for row in work_order.receivables}
		self.assertEqual(by_item["FRONT-BLACK-M"].cost, 1)
		self.assertEqual(by_item["BACK-BLACK-M"].cost, 1)
		self.assertEqual(by_item["SLEEVE-BLACK-M"].cost, 0.5)
		self.assertEqual(sum(row.total_cost for row in work_order.receivables), 30)

	def test_size_rate_uses_the_same_panel_type_split_for_each_garment_variant(self):
		work_order = _work_order()
		_add_garment_rows(work_order, colour="Navy", size="M", quantity=20)
		process_cost = frappe._dict(
			name="TEST-SIZE-PROCESS-COST",
			depends_on_attribute=1,
			attribute="Size",
		)
		ipd = _ipd()
		attributes = _variant_attributes("Black", "M") | _variant_attributes("Navy", "M")

		with (
			patch(
				"essdee_yrp.overrides.work_order.frappe.get_cached_doc",
				return_value=ipd,
			),
			patch(
				"essdee_yrp.overrides.work_order.get_variant_attributes",
				side_effect=lambda item_variant: attributes[item_variant],
			),
			patch(
				"essdee_yrp.overrides.work_order.get_process_cost_rate",
				return_value=4,
			),
		):
			work_order.apply_receivable_process_costs(process_cost)

		by_item = {row.item_variant: row for row in work_order.receivables}
		for colour in ("Black", "Navy"):
			self.assertAlmostEqual(by_item[f"FRONT-{colour.upper()}-M"].cost, 4 / 3)
			self.assertAlmostEqual(by_item[f"BACK-{colour.upper()}-M"].cost, 4 / 3)
			self.assertAlmostEqual(by_item[f"SLEEVE-{colour.upper()}-M"].cost, 2 / 3)
		self.assertEqual(sum(row.total_cost for row in work_order.receivables), 120)

	def test_flat_garment_rate_is_spread_across_the_printed_panel_types(self):
		work_order = _work_order()
		work_order.receivables = [
			row for row in work_order.receivables if not row.item_variant.startswith("SLEEVE")
		]
		process_cost = frappe._dict(
			name="TEST-FLAT-PROCESS-COST",
			depends_on_attribute=0,
			attribute=None,
			process_cost_values=[frappe._dict(attribute_value=None, min_order_qty=0, price=4)],
		)
		attributes = _variant_attributes("Black", "M")

		with (
			patch(
				"essdee_yrp.overrides.work_order.frappe.get_cached_doc",
				return_value=_ipd(),
			),
			patch(
				"essdee_yrp.overrides.work_order.get_variant_attributes",
				side_effect=lambda item_variant: attributes[item_variant],
			),
		):
			work_order.apply_receivable_process_costs(process_cost)

		by_item = {row.item_variant: row for row in work_order.receivables}
		self.assertEqual(by_item["FRONT-BLACK-M"].cost, 2)
		self.assertEqual(by_item["BACK-BLACK-M"].cost, 2)
		self.assertEqual(sum(row.total_cost for row in work_order.receivables), 40)

	def test_cutting_flat_rate_skips_other_item_rows_and_splits_across_panels(self):
		work_order = _work_order()
		work_order.append("receivables", {"item_variant": "CLOTH-BLACK", "qty": 2.5, "set_combination": "{}"})
		process_cost = frappe._dict(
			name="TEST-FLAT-PROCESS-COST",
			item="GARMENT",
			depends_on_attribute=0,
			attribute=None,
			process_cost_values=[frappe._dict(attribute_value=None, min_order_qty=0, price=3)],
		)
		attributes = {
			**_variant_attributes("Black", "M"),
			"CLOTH-BLACK": {"Colour": "Black", "Dia": "26 Dia"},
		}

		with (
			patch("essdee_yrp.overrides.work_order.frappe.get_cached_doc", return_value=_ipd()),
			patch(
				"essdee_yrp.overrides.work_order.get_variant_attributes",
				side_effect=lambda item_variant: attributes[item_variant],
			),
			patch(
				"yrp.yrp.doctype.yrp_work_order.yrp_work_order.get_variant_items",
				side_effect=lambda variants: {
					v: "CLOTH" if v.startswith("CLOTH") else "GARMENT" for v in variants
				},
			),
		):
			work_order.apply_receivable_process_costs(process_cost)

		by_item = {row.item_variant: row for row in work_order.receivables}
		self.assertEqual(by_item["FRONT-BLACK-M"].cost, 1)
		self.assertEqual(by_item["BACK-BLACK-M"].cost, 1)
		self.assertEqual(by_item["SLEEVE-BLACK-M"].cost, 0.5)
		self.assertEqual(by_item["CLOTH-BLACK"].cost, 0)
		self.assertEqual(by_item["CLOTH-BLACK"].total_cost, 0)
		self.assertAlmostEqual(sum(row.total_cost for row in work_order.receivables), 30)

	def test_dependent_cost_without_attribute_splits_like_flat_cost(self):
		def costs(depends_on_attribute, attribute, attribute_value):
			work_order = _work_order()
			process_cost = frappe._dict(
				name="TEST-FLAT-PROCESS-COST",
				depends_on_attribute=depends_on_attribute,
				attribute=attribute,
				process_cost_values=[frappe._dict(attribute_value=attribute_value, min_order_qty=0, price=2)],
			)
			attributes = _variant_attributes("Black", "M")
			with (
				patch("essdee_yrp.overrides.work_order.frappe.get_cached_doc", return_value=_ipd()),
				patch(
					"essdee_yrp.overrides.work_order.get_variant_attributes",
					side_effect=lambda item_variant: attributes[item_variant],
				),
				patch(
					"yrp.yrp.doctype.yrp_work_order.yrp_work_order.get_variant_attributes",
					side_effect=lambda item_variant: attributes[item_variant],
				),
			):
				work_order.apply_receivable_process_costs(process_cost)
			return {row.item_variant: (row.cost, row.total_cost) for row in work_order.receivables}

		flat = costs(0, None, None)
		self.assertAlmostEqual(flat["FRONT-BLACK-M"][0], 2 / 3)
		self.assertAlmostEqual(sum(total for _cost, total in flat.values()), 20)
		for attribute, attribute_value in ((None, None), ("", ""), (None, "")):
			self.assertEqual(costs(1, attribute, attribute_value), flat)

	def test_stage_attribute_keeps_its_direct_per_panel_rate(self):
		work_order = _work_order()
		process_cost = frappe._dict(
			name="TEST-STAGE-PROCESS-COST",
			depends_on_attribute=1,
			attribute="Stage",
			process_cost_values=[frappe._dict(attribute_value="Cut", min_order_qty=0, price=1.5)],
		)
		attributes = _variant_attributes("Black", "M")

		with (
			patch("essdee_yrp.overrides.work_order.frappe.get_cached_doc", return_value=_ipd()),
			patch(
				"essdee_yrp.overrides.work_order.get_variant_attributes",
				side_effect=lambda item_variant: attributes[item_variant],
			),
			patch(
				"yrp.yrp.doctype.yrp_work_order.yrp_work_order.get_variant_attributes",
				side_effect=lambda item_variant: attributes[item_variant],
			),
		):
			work_order.apply_receivable_process_costs(process_cost)

		self.assertEqual([row.cost for row in work_order.receivables], [1.5, 1.5, 1.5])

	def test_set_part_price_is_split_across_that_parts_panels(self):
		work_order = _set_work_order()
		process_cost = frappe._dict(
			name="TEST-PART-PROCESS-COST",
			depends_on_attribute=1,
			attribute="Part",
			process_cost_values=[
				frappe._dict(attribute_value="Top", min_order_qty=0, price=4),
				frappe._dict(attribute_value="Bottom", min_order_qty=0, price=6),
			],
		)
		by_item = _apply_set_process_cost(work_order, process_cost)

		self.assertEqual(by_item["FRONT"].cost, 2)
		self.assertEqual(by_item["SLEEVE"].cost, 1)
		self.assertEqual(by_item["LEG"].cost, 1.5)
		self.assertEqual(by_item["POCKET"].cost, 3)
		self.assertAlmostEqual(sum(row.total_cost for row in work_order.receivables), 100)

	def test_set_flat_rate_is_split_across_all_panels_of_the_set(self):
		work_order = _set_work_order()
		process_cost = frappe._dict(
			name="TEST-FLAT-PROCESS-COST",
			depends_on_attribute=0,
			attribute=None,
			process_cost_values=[frappe._dict(attribute_value=None, min_order_qty=0, price=4)],
		)
		by_item = _apply_set_process_cost(work_order, process_cost)

		self.assertEqual(by_item["FRONT"].cost, 1)
		self.assertEqual(by_item["SLEEVE"].cost, 0.5)
		self.assertEqual(by_item["LEG"].cost, 0.5)
		self.assertEqual(by_item["POCKET"].cost, 1)
		self.assertAlmostEqual(sum(row.total_cost for row in work_order.receivables), 40)

	def test_cutting_panel_price_is_divided_by_panel_quantity_per_garment(self):
		work_order = _set_work_order()
		process_cost = frappe._dict(
			name="TEST-PANEL-PROCESS-COST",
			depends_on_attribute=1,
			attribute="Panel",
			process_cost_values=[
				frappe._dict(attribute_value=panel, min_order_qty=0, price=1)
				for panel in ("Front", "Sleeve", "Leg", "Pocket")
			],
		)
		by_item = _apply_set_process_cost(work_order, process_cost)

		self.assertEqual(by_item["FRONT"].cost, 1)
		self.assertEqual(by_item["SLEEVE"].cost, 0.5)
		self.assertEqual(by_item["LEG"].cost, 0.5)
		self.assertEqual(by_item["POCKET"].cost, 1)

	def test_panel_attribute_keeps_its_direct_per_panel_rate(self):
		work_order = _work_order()
		process_cost = frappe._dict(
			name="TEST-PANEL-PROCESS-COST",
			depends_on_attribute=1,
			attribute="Panel",
			process_cost_values=[
				frappe._dict(attribute_value="Front", min_order_qty=0, price=3),
				frappe._dict(attribute_value="Back", min_order_qty=0, price=2),
				frappe._dict(attribute_value="Sleeve", min_order_qty=0, price=1),
			],
		)
		attributes = _variant_attributes("Black", "M")

		with (
			patch(
				"essdee_yrp.overrides.work_order.frappe.get_cached_doc",
				return_value=_ipd(),
			),
			patch(
				"yrp.yrp.doctype.yrp_work_order.yrp_work_order.get_variant_attributes",
				side_effect=lambda item_variant: attributes[item_variant],
			),
		):
			work_order.apply_receivable_process_costs(process_cost)

		by_item = {row.item_variant: row for row in work_order.receivables}
		self.assertEqual(by_item["FRONT-BLACK-M"].cost, 3)
		self.assertEqual(by_item["BACK-BLACK-M"].cost, 2)
		self.assertEqual(by_item["SLEEVE-BLACK-M"].cost, 1)

	def test_pc_25_oracle_conserves_colour_value_with_panel_type_split(self):
		if not frappe.db.exists("YRP Work Order", "YRP-WO-2026-00058"):
			self.skipTest("YRP-WO-2026-00058 is unavailable")
		if not frappe.db.exists("YRP Process Cost", "YRP-PC-00025"):
			self.skipTest("YRP-PC-00025 is unavailable")

		work_order = frappe.get_doc("YRP Work Order", "YRP-WO-2026-00058")
		process_cost = frappe.get_doc("YRP Process Cost", "YRP-PC-00025")
		self.assertIsInstance(work_order, EssdeeWorkOrder)
		work_order.apply_receivable_process_costs(process_cost)

		colour_totals = {"Black": 0, "Mint": 0, "Navy": 0, "Olive": 0}
		front_rate = None
		sleeve_rate = None
		for row in work_order.receivables:
			attributes = get_variant_attributes(row.item_variant)
			colour_totals[attributes["Colour"]] += row.total_cost
			if attributes["Colour"] == "Black" and attributes["Size"] == "45 cm":
				if attributes["Panel"] == "Top Front":
					front_rate = row.cost
				elif attributes["Panel"] == "Sleeve 1":
					sleeve_rate = row.cost

		self.assertAlmostEqual(front_rate, 5 / 9, places=8)
		self.assertAlmostEqual(sleeve_rate, 5 / 18, places=8)
		self.assertAlmostEqual(colour_totals["Black"], 3000, places=4)
		self.assertAlmostEqual(colour_totals["Mint"], 3000, places=4)
		self.assertAlmostEqual(colour_totals["Navy"], 3000, places=4)
		self.assertAlmostEqual(colour_totals["Olive"], 2400, places=4)


def _work_order():
	work_order = EssdeeWorkOrder({"doctype": "YRP Work Order", "production_detail": "TEST-IPD"})
	_add_garment_rows(work_order, colour="Black", size="M", quantity=10)
	return work_order


def _add_garment_rows(work_order, colour, size, quantity):
	combination = frappe.as_json({"major_colour": colour})
	colour_key = colour.upper()
	work_order.append(
		"work_order_calculated_items",
		{
			"item_variant": f"GARMENT-{colour_key}-{size}",
			"quantity": quantity,
			"set_combination": combination,
		},
	)
	for item_variant, panel_quantity in (
		(f"FRONT-{colour_key}-{size}", quantity),
		(f"BACK-{colour_key}-{size}", quantity),
		(f"SLEEVE-{colour_key}-{size}", quantity * 2),
	):
		work_order.append(
			"receivables",
			{
				"item_variant": item_variant,
				"qty": panel_quantity,
				"set_combination": combination,
			},
		)


def _set_work_order():
	work_order = EssdeeWorkOrder(
		{"doctype": "YRP Work Order", "production_detail": "TEST-SET-IPD", "process_name": "Cutting"}
	)
	combination = frappe.as_json({"major_colour": "Black", "major_part": "Top"})
	for part in ("TOP", "BOTTOM"):
		work_order.append(
			"work_order_calculated_items",
			{"item_variant": f"SET-{part}", "quantity": 10, "set_combination": combination},
		)
	for item_variant, quantity in (("FRONT", 10), ("SLEEVE", 20), ("LEG", 20), ("POCKET", 10)):
		work_order.append(
			"receivables",
			{"item_variant": item_variant, "qty": quantity, "set_combination": combination},
		)
	return work_order


def _apply_set_process_cost(work_order, process_cost):
	ipd = frappe._dict(
		_ipd(),
		is_set_item=1,
		set_item_attribute="Part",
		cutting_process="Cutting",
		stiching_item_details=[
			frappe._dict(stiching_attribute_value=panel, set_item_attribute_value=part, quantity=quantity)
			for panel, part, quantity in (
				("Front", "Top", 1),
				("Sleeve", "Top", 2),
				("Leg", "Bottom", 2),
				("Pocket", "Bottom", 1),
			)
		],
	)
	base = {"Colour": "Black", "Size": "M"}
	attributes = {
		"SET-TOP": {**base, "Stage": "Piece", "Part": "Top"},
		"SET-BOTTOM": {**base, "Stage": "Piece", "Part": "Bottom"},
		**{
			item_variant: {**base, "Stage": "Cut", "Panel": item_variant.title()}
			for item_variant in ("FRONT", "SLEEVE", "LEG", "POCKET")
		},
	}
	with (
		patch("essdee_yrp.overrides.work_order.frappe.get_cached_doc", return_value=ipd),
		patch(
			"essdee_yrp.overrides.work_order.get_variant_attributes",
			side_effect=lambda item_variant: attributes[item_variant],
		),
		patch(
			"yrp.yrp.doctype.yrp_work_order.yrp_work_order.get_variant_attributes",
			side_effect=lambda item_variant: attributes[item_variant],
		),
	):
		work_order.apply_receivable_process_costs(process_cost)
	return {row.item_variant: row for row in work_order.receivables}


def _ipd():
	return frappe._dict(
		stiching_attribute="Panel",
		packing_attribute="Colour",
		primary_item_attribute="Size",
		dependent_attribute="Stage",
	)


def _variant_attributes(colour, size):
	colour_key = colour.upper()
	base = {"Colour": colour, "Size": size}
	return {
		f"GARMENT-{colour_key}-{size}": {**base, "Stage": "Piece"},
		f"FRONT-{colour_key}-{size}": {**base, "Stage": "Cut", "Panel": "Front"},
		f"BACK-{colour_key}-{size}": {**base, "Stage": "Cut", "Panel": "Back"},
		f"SLEEVE-{colour_key}-{size}": {**base, "Stage": "Cut", "Panel": "Sleeve"},
	}
