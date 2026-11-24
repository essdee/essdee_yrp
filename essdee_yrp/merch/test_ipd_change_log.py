import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.merch.ipd import change_log
from essdee_yrp.merch.ipd.fields import DOCTYPE


def ipd(**values):
	return frappe.get_doc(
		{"doctype": DOCTYPE, "name": "TEST-IPD", "item": "TEST-ITEM", "packing_attribute": "Colour", **values}
	)


def bom(*items):
	return [{"item": item, "qty_of_product": 1, "qty_of_bom_item": 1, "uom": "Nos"} for item in items]


def accessories(*names):
	items = [{"Colour": "White", "Accessory": name, "Dia": "30 Dia", "Weight": 0.006} for name in names]
	return json.dumps({"attributes": ["Colour", "Accessory", "Dia", "Weight"], "items": items})


def set_combinations(*colours):
	return [
		{"major_attribute_value": "White", "set_item_attribute_value": "Top", "attribute_value": colour}
		for colour in colours
	]


class TestIpdChangeLines(IntegrationTestCase):
	def lines(self, before, after):
		return change_log.get_change_lines(ipd(**before), ipd(**after))

	def test_bom_items_added_and_removed(self):
		lines = self.lines(
			{"item_bom": bom("Flag Woven Label", "Twill Tape", "Elastic")},
			{"item_bom": bom("Elastic", "Inner Elastic", "Plain Poly Bag Small")},
		)
		self.assertEqual(
			lines,
			[
				"Added BOM items: Inner Elastic, Plain Poly Bag Small",
				"Removed BOM items: Flag Woven Label, Twill Tape",
			],
		)

	def test_bom_item_added_for_another_process(self):
		before = [
			{"item": "Poly Bag", "process_name": "Stitching"},
			{"item": "Tag", "process_name": "Packing"},
		]
		after = [
			*before,
			{"item": "Poly Bag", "process_name": "Packing"},
			{"item": "Inner Card", "process_name": "Packing"},
		]
		lines = self.lines({"item_bom": before}, {"item_bom": after})
		self.assertEqual(lines, ["Added BOM items: Poly Bag (Packing), Inner Card"])

	def test_duplicate_bom_row_added_and_removed(self):
		before = [
			{"item": "Plain Poly Bag-Small", "process_name": "Packing"},
			{"item": "Inner Card Small", "process_name": "Ironing"},
		]
		added = [
			{"item": "Plain Poly Bag-Small", "process_name": "Packing"},
			{"item": "Inner Card-Small", "process_name": "Packing"},
		]
		self.assertEqual(
			self.lines({"item_bom": before}, {"item_bom": before + added}),
			["Added BOM items: Plain Poly Bag-Small, Inner Card-Small"],
		)
		self.assertEqual(
			self.lines({"item_bom": before + added}, {"item_bom": before}),
			["Removed BOM items: Plain Poly Bag-Small, Inner Card-Small"],
		)

	def test_same_bom_row_added_twice_shows_count(self):
		row = {"item": "Elastic", "process_name": "Stitching"}
		lines = self.lines(
			{"item_bom": [row]}, {"item_bom": [row, row, row, {**row, "process_name": "Packing"}]}
		)
		self.assertEqual(lines, ["Added BOM items: Elastic (Stitching) ×2, Elastic (Packing)"])

	def test_item_changed_in_place_is_logged_as_swap(self):
		lines = self.lines(
			{"item_bom": [{"item": "Elastic", "process_name": "Stitching"}]},
			{"item_bom": [{"item": "Twill Tape", "process_name": "Stitching"}]},
		)
		self.assertEqual(lines, ["Added BOM items: Twill Tape", "Removed BOM items: Elastic"])

	def test_reorder_and_qty_edits_are_not_logged(self):
		after = list(reversed(bom("A", "B")))
		after[0]["qty_of_bom_item"] = 5
		self.assertEqual(self.lines({"item_bom": bom("A", "B")}, {"item_bom": after}), [])

	def test_packing_colours(self):
		before = [{"attribute_value": "White"}, {"attribute_value": "Red"}]
		after = [{"attribute_value": "White"}, {"attribute_value": "Navy"}, {"attribute_value": "Black"}]
		lines = self.lines(
			{"packing_attribute_details": before, "packing_attribute_no": 2},
			{"packing_attribute_details": after, "packing_attribute_no": 3},
		)
		self.assertEqual(lines, ["Packing colour added: Navy, Black", "Packing colour removed: Red"])

	def test_unknown_attribute_value_id_falls_back_to_raw_id(self):
		lines = self.lines(
			{"packing_attribute_details": [{"attribute_value": "White"}]},
			{
				"packing_attribute_details": [
					{"attribute_value": "White"},
					{"attribute_value": "IAV-MISSING-TEST"},
				]
			},
		)
		self.assertEqual(lines, ["Packing colour added: IAV-MISSING-TEST"])

	def test_packing_attribute_change_labels_each_side(self):
		lines = self.lines(
			{"packing_attribute": "Colour", "packing_attribute_details": [{"attribute_value": "White"}]},
			{"packing_attribute": "Size", "packing_attribute_details": [{"attribute_value": "S"}]},
		)
		self.assertEqual(lines, ["Packing size added: S", "Packing colour removed: White"])

	def test_set_item_colours(self):
		lines = self.lines(
			{"set_item_combination_details": set_combinations("White", "Grey")},
			{"set_item_combination_details": set_combinations("White", "White", "Navy")},
		)
		self.assertEqual(lines, ["Set item colour added: Navy", "Set item colour removed: Grey"])

	def test_set_item_colour_qualified_by_set_item_only_when_ambiguous(self):
		bottom = {
			"major_attribute_value": "White",
			"set_item_attribute_value": "Bottom",
			"attribute_value": "Navy",
		}
		lines = self.lines(
			{"set_item_combination_details": set_combinations("Navy")},
			{"set_item_combination_details": [*set_combinations("Navy"), bottom]},
		)
		self.assertEqual(lines, ["Set item colour added: Navy (Bottom)"])

	def test_rebuilt_rows_with_same_values_are_not_logged(self):
		lines = self.lines(
			{"packing_attribute_details": [{"attribute_value": "Navy"}, {"attribute_value": "Navy"}]},
			{"packing_attribute_details": [{"attribute_value": "Navy"}, {"attribute_value": "Navy"}]},
		)
		self.assertEqual(lines, [])

	def test_accessory_rows_dropped_with_a_colour_are_not_logged(self):
		lines = self.lines(
			{"cloth_accessory_json": accessories("Folding", "Folding", "Folding")},
			{"cloth_accessory_json": accessories("Folding")},
		)
		self.assertEqual(lines, [])

	def test_stitching_panels(self):
		lines = self.lines(
			{
				"stiching_item_details": [
					{"stiching_attribute_value": "Front"},
					{"stiching_attribute_value": "Back"},
				]
			},
			{
				"stiching_item_details": [
					{"stiching_attribute_value": "Front"},
					{"stiching_attribute_value": "Pocket"},
				]
			},
		)
		self.assertEqual(lines, ["Stitching panel added: Pocket", "Stitching panel removed: Back"])

	def test_cloth_accessories(self):
		lines = self.lines(
			{"cloth_accessory_json": accessories("Rib", "Collar")},
			{"cloth_accessory_json": accessories("Rib", "Tape")},
		)
		self.assertEqual(lines, ["Cloth accessory added: Tape", "Cloth accessory removed: Collar"])

	def test_other_changes_are_not_logged(self):
		cloth = {"name1": "Main", "cloth": "Cotton", "required_gsm": 180}
		lines = self.lines(
			{"approval_status": "Not Approved", "additional_cloth": 0, "cloth_detail": [cloth]},
			{
				"approval_status": "Approved",
				"additional_cloth": 2,
				"cloth_detail": [{**cloth, "required_gsm": 200}],
			},
		)
		self.assertEqual(lines, [])


class TestIpdChangeComment(IntegrationTestCase):
	def test_one_comment_per_save(self):
		after = ipd(item_bom=bom("Elastic"))
		after.get_doc_before_save = lambda: ipd(item_bom=bom("Twill Tape"))
		with patch.object(change_log, "add_change_comment") as add:
			change_log.on_update(after)
		add.assert_called_once_with("TEST-IPD", ["Added BOM items: Elastic", "Removed BOM items: Twill Tape"])

	def test_no_comment_without_change_or_on_insert(self):
		unchanged = ipd(item_bom=bom("Elastic"))
		unchanged.get_doc_before_save = lambda: ipd(item_bom=bom("Elastic"))
		new = ipd()
		new.get_doc_before_save = lambda: None
		with patch.object(change_log, "add_change_comment") as add:
			change_log.on_update(unchanged)
			change_log.on_update(new)
		add.assert_not_called()

	def test_comment_is_escaped_and_stored(self):
		name = frappe.db.get_value(DOCTYPE, {}, "name")
		change_log.add_change_comment(name, ["Added BOM items: <b>Tape</b>", "Packing colour added: Navy"])
		content = frappe.db.get_value(
			"Comment",
			{"reference_doctype": DOCTYPE, "reference_name": name, "comment_type": "Comment"},
			"content",
			order_by="creation desc",
		)
		self.assertEqual(content, "Added BOM items: &lt;b&gt;Tape&lt;/b&gt;<br>Packing colour added: Navy")
