from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet import sd_yrp_cutting_laysheet as cutting


class TestCuttingAccessoryReceipts(TestCase):
	def test_accessory_receipt_is_added_with_empty_combination(self):
		lay = frappe._dict(
			cutting_laysheet_bundles=[],
			cutting_laysheet_accessory_details=[
				frappe._dict(cloth_item_variant="FOLDING-GREY", weight=20),
				frappe._dict(cloth_item_variant="FOLDING-GREY", weight=5),
			],
		)
		defaults = {
			"items": [
				dict(
					item_variant="FOLDING-GREY",
					quantity=0,
					received_type="Accepted",
					set_combination="{}",
					ref_docname="WO-ACCESSORY",
				)
			]
		}
		with (
			patch.object(
				cutting.frappe, "get_value", return_value=("Size", "Colour", "Panel", "Cut", "Stage")
			),
			patch.object(
				cutting.frappe, "get_cached_doc", return_value=frappe._dict(stiching_item_details=[])
			),
			patch.object(cutting.frappe.db, "get_single_value", return_value="Accepted"),
			patch(
				"yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note.get_work_order_defaults",
				return_value=defaults,
			),
			patch(
				"essdee_yrp.overrides.goods_received_note.normalize_cutting_grn_row_indexes",
				side_effect=lambda rows: rows,
			),
		):
			_, rows = cutting._cutting_grn_output_rows(lay, frappe._dict(name="WO"), "Garment", "IPD")
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].quantity, 25)
		self.assertEqual(rows[0].ref_docname, "WO-ACCESSORY")

	def test_accessory_value_is_not_distributed_to_panels(self):
		accessory = frappe._dict(name="ACCESSORY", stock_qty=20)
		panels = [frappe._dict(name="FRONT", stock_qty=100), frappe._dict(name="BACK", stock_qty=100)]
		allocations = cutting._allocate_cutting_input(20, 20, [accessory], panels)
		self.assertEqual([(r.name, q) for r, q in allocations], [("ACCESSORY", 20)])
		self.assertEqual(sum(q * 320 for _, q in allocations), 6400)

	def test_same_fabric_can_supply_panels_and_accessory(self):
		accessory = frappe._dict(name="ACCESSORY", stock_qty=20)
		panels = [frappe._dict(name="FRONT", stock_qty=1), frappe._dict(name="BACK", stock_qty=2)]
		allocations = cutting._allocate_cutting_input(50, 20, [accessory], panels)
		self.assertEqual(
			[(r.name, q) for r, q in allocations], [("ACCESSORY", 20), ("FRONT", 10), ("BACK", 20)]
		)
		self.assertEqual(sum(q for _, q in allocations), 50)

	def test_missing_accessory_receipt_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			cutting._allocate_cutting_input(20, 20, [], [frappe._dict(stock_qty=100)])

	def test_consumed_cloth_rows_record_their_lay_colours(self):
		lay = frappe._dict(
			cutting_laysheet_details=[
				frappe._dict(cloth_item_variant="CLOTH-BLACK", colour="Black", used_weight=6),
				frappe._dict(cloth_item_variant="CLOTH-BLACK", colour="Black", used_weight=4),
				frappe._dict(cloth_item_variant="CLOTH-NAVY", colour="Navy", used_weight=5),
			],
			cutting_laysheet_accessory_details=[],
		)
		with (
			patch.object(cutting, "get_parent_item", return_value="Cloth"),
			patch.object(cutting.frappe, "get_cached_value", return_value="Kg"),
		):
			rows = cutting._cutting_grn_consumed_rows(lay)
		self.assertEqual(
			[(row["item_variant"], row["qty"], row["colours"]) for row in rows],
			[("CLOTH-BLACK", 10, {"Black"}), ("CLOTH-NAVY", 5, {"Navy"})],
		)

	def test_each_colour_cloth_is_spread_only_over_its_own_panels(self):
		work_order = frappe._dict(
			name="WO-1",
			production_detail="IPD-1",
			deliverables=[
				frappe._dict(name="IN-BLACK", item_variant="CLOTH-BLACK", uom="Kg", is_calculated=1),
				frappe._dict(name="IN-NAVY", item_variant="CLOTH-NAVY", uom="Kg", is_calculated=1),
			],
		)
		grn = frappe._dict(
			cutting_laysheet="CLS-1",
			against_id="WO-1",
			from_warehouse="CUT-WH",
			posting_date="2026-11-23",
			posting_time="10:00:00",
			items=[
				frappe._dict(name="BLACK-FRONT", item_variant="PANEL-BLACK-FRONT", stock_qty=10),
				frappe._dict(name="BLACK-BACK", item_variant="PANEL-BLACK-BACK", stock_qty=10),
				frappe._dict(name="NAVY-FRONT", item_variant="PANEL-NAVY-FRONT", stock_qty=20),
				frappe._dict(name="NAVY-BACK", item_variant="PANEL-NAVY-BACK", stock_qty=20),
			],
		)
		consumed = [
			{"item_variant": "CLOTH-BLACK", "uom": "Kg", "qty": 10, "colours": {"Black"}},
			{"item_variant": "CLOTH-NAVY", "uom": "Kg", "qty": 4, "colours": {"Navy"}},
		]
		with (
			patch.object(
				cutting.frappe,
				"get_doc",
				side_effect=lambda doctype, _name: (
					frappe._dict(name="CLS-1", cutting_plan="CP-1", cutting_laysheet_accessory_details=[])
					if doctype == "SD YRP Cutting LaySheet"
					else work_order
				),
			),
			patch.object(cutting.frappe.db, "get_value", return_value="WO-1"),
			patch.object(cutting.frappe, "get_cached_value", return_value="Colour"),
			patch.object(cutting, "_cutting_grn_consumed_rows", return_value=consumed),
			patch.object(
				cutting,
				"get_variant_attr_details",
				side_effect=lambda variant: {"Colour": variant.split("-")[1].title()},
			),
			patch("yrp.stock.utils.get_conversion_factor", return_value={"conversion_factor": 1}),
			patch("yrp.yrp.doctype.yrp_work_order.yrp_work_order._stock_dimension_values", return_value={}),
			patch("yrp.stock.utils.get_stock_balance", return_value=(100, 300)),
		):
			plan = cutting.calculate_cutting_consumption_plan(grn)
		shares = {(row["goods_received_note_item"], row["item_variant"]): row["stock_qty"] for row in plan}
		self.assertEqual(
			shares,
			{
				("BLACK-FRONT", "CLOTH-BLACK"): 5,
				("BLACK-BACK", "CLOTH-BLACK"): 5,
				("NAVY-FRONT", "CLOTH-NAVY"): 2,
				("NAVY-BACK", "CLOTH-NAVY"): 2,
			},
		)

	def test_colour_cloth_without_its_own_panels_is_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "panel receipt rows"):
			cutting._allocate_cutting_input(5, 0, [], [])
