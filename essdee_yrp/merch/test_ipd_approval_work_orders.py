import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.merch import ipd_workspace as workspace
from essdee_yrp.merch.ipd.approval.work_orders import get_changes, quantity_grid

STAGES = {"stiching_process": "Stitching", "cutting_process": "Cutting", "packing_process": "Packing"}
LABELS = {"stiching_accessory_json": "Stitching Accessory", "tech_pack_version": "Tech Pack Version"}


def row(variant, colour, size, qty):
	return {"variant": variant, "colour": colour, "size": size, "qty": qty}


def approval():
	return {"changed": [["approval_status", "Not Approved", "Approved"]]}


def changes(*versions, bom=None):
	return get_changes(list(versions), STAGES, bom or {}, LABELS)


class TestQuantityGrid(IntegrationTestCase):
	def test_panels_of_one_piece_count_once(self):
		grid = quantity_grid(
			[
				row("Front-Black-S", "Black", "S", 10),
				row("Back-Black-S", "Black", "S", 10),
				row("Front-Black-M", "Black", "M", 4),
				row("Front-Black-M", "Black", "M", 2),
			],
			["Black", "Navy"],
			["S", "M", "L"],
		)
		self.assertEqual(grid["colours"], ["Black"])
		self.assertEqual(grid["sizes"], ["S", "M"])
		self.assertEqual(grid["cells"], [[10, 6]])
		self.assertEqual(grid["total"], 16)

	def test_ipd_order_wins_and_unknown_values_follow(self):
		grid = quantity_grid(
			[row("a", "Navy", "L", 1), row("b", "Black", "S", 2), row("c", "Teal", "XS", 3)],
			["Black", "Navy"],
			["S", "M", "L"],
		)
		self.assertEqual(grid["colours"], ["Black", "Navy", "Teal"])
		self.assertEqual(grid["sizes"], ["S", "L", "XS"])
		self.assertEqual(grid["cells"], [[2, None, None], [None, 1, None], [None, None, 3]])

	def test_set_items_count_sets_under_the_major_colour(self):
		set_combination = '{"major_part": "Top", "major_colour": "Navy"}'
		rows = [
			{**row("Top-Front-Navy-S", "Navy", "S", 10), "set_combination": set_combination},
			{**row("Top-Back-Navy-S", "Navy", "S", 10), "set_combination": set_combination},
			{**row("Bottom-Front-Maroon-S", "Maroon", "S", 10), "set_combination": set_combination},
			{**row("Bottom-Back-Maroon-S", "Maroon", "S", 10), "set_combination": set_combination},
		]
		grid = quantity_grid(rows, ["Navy", "Maroon"], ["S"])
		self.assertEqual((grid["colours"], grid["cells"], grid["total"]), (["Navy"], [[10]], 10))

	def test_rows_without_attributes_still_count(self):
		grid = quantity_grid([row("a", None, None, 5)], [], [])
		self.assertEqual((grid["colours"], grid["sizes"], grid["cells"]), ([""], [""], [[5]]))

	def test_no_rows_give_an_empty_grid(self):
		self.assertEqual(quantity_grid([], ["Black"], ["S"])["total"], 0)


class TestApprovalChanges(IntegrationTestCase):
	def test_never_approved_ipd_has_no_changes(self):
		result = changes({"added": [["item_bom", {"process_name": "Stitching", "item": "Label"}]]})
		self.assertEqual(result, {"since_approval": False, "processes": []})

	def test_bom_rows_added_after_the_last_approval_flag_their_process(self):
		result = changes(
			{"added": [["item_bom", {"process_name": "Stitching", "item": "Poly Bag"}]]},
			{"removed": [["item_bom", {"process_name": "Packing", "item": "Tag"}]]},
			approval(),
			{"added": [["item_bom", {"process_name": "Cutting", "item": "Before approval"}]]},
		)
		self.assertTrue(result["since_approval"])
		self.assertEqual(
			result["processes"],
			[
				{"process": "Packing", "changes": ["BOM item removed: Tag"]},
				{"process": "Stitching", "changes": ["BOM item added: Poly Bag"]},
			],
		)

	def test_changed_bom_row_is_found_from_the_current_rows(self):
		result = changes(
			{"row_changed": [["item_bom", 2, "bom-2", [["qty_of_bom_item", 1, 2]]]]},
			approval(),
			bom={"bom-2": {"process_name": "Stitching", "item": "Elastic"}},
		)
		self.assertEqual(
			result["processes"], [{"process": "Stitching", "changes": ["BOM item changed: Elastic"]}]
		)

	def test_stage_fields_map_to_the_ipd_stage_process(self):
		result = changes({"changed": [["stiching_accessory_json", "{}", {"a": 1}]]}, approval())
		self.assertEqual(
			result["processes"], [{"process": "Stitching", "changes": ["Stitching Accessory changed"]}]
		)

	def test_json_resaved_without_a_real_change_is_ignored(self):
		result = changes(
			{"changed": [["cutting_cloths_json", '{"items": [1]}', {"items": [1]}]]},
			{"changed": [["tech_pack_version", "1", "2"]]},
			approval(),
		)
		self.assertEqual(result["processes"], [])

	def test_embellishment_changes_flag_only_the_changed_process(self):
		result = changes(
			{
				"changed": [
					[
						"emblishment_details_json",
						'{"Printing": ["Front"], "Yolk Fusing": ["Back"]}',
						{"Printing": ["Front", "Back"], "Yolk Fusing": ["Back"]},
					]
				]
			},
			approval(),
		)
		self.assertEqual(
			result["processes"], [{"process": "Printing", "changes": ["Embellishment panels changed"]}]
		)


class TestApprovalWorkOrdersEndpoint(IntegrationTestCase):
	def test_lists_submitted_work_orders_of_the_ipd_lots(self):
		ipd = frappe.db.get_value("YRP Work Order", {"docstatus": 1}, "production_detail")
		if not ipd:
			self.skipTest("No submitted Work Order on this site")
		result = workspace.get_ipd_approval_work_orders(ipd)
		names = {order["name"] for order in result["orders"]}
		expected = set(
			frappe.get_all("YRP Work Order", {"docstatus": 1, "production_detail": ipd}, pluck="name")
		)
		self.assertTrue(expected <= names)
		self.assertTrue(all(order["grid"]["total"] >= 0 for order in result["orders"]))

	def test_ipd_without_work_orders_lists_none(self):
		ipd = frappe.db.sql(
			"""select ipd.name from `tabYRP Item Production Detail` ipd
			where not exists (select 1 from `tabYRP Work Order` wo where wo.production_detail = ipd.name)
			and not exists (select 1 from `tabSD YRP Lot` lot where lot.production_detail = ipd.name)
			limit 1"""
		)
		ipd = ipd[0][0] if ipd else None
		if not ipd:
			self.skipTest("Every IPD has Work Orders")
		self.assertEqual(workspace.get_ipd_approval_work_orders(ipd)["orders"], [])
