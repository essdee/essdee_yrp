import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.merch import ipd_workspace as workspace
from essdee_yrp.merch.ipd.approval.summary import SECTION_LABELS, build_summary
from essdee_yrp.merch.ipd_test_support import SAMPLES

SIZES = ["S", "M", "L", "XL"]


def grid(attributes, items):
	return {"attributes": [*attributes, "Dia", "Weight"], "items": items}


FRONT_ONLY = [{"stiching_attribute_value": "Front", "quantity": 1, "category": "Body"}]


def summary(**values):
	base = {
		"primary_item_attribute": "Size",
		"packing_attribute": "Colour",
		"stiching_attribute": "Panel",
		"stiching_in_stage": "Cut",
		"packing_attribute_details": [{"attribute_value": "Black"}, {"attribute_value": "Navy"}],
		"stiching_item_details": [
			{"stiching_attribute_value": "Front", "quantity": 1, "category": "Body"},
			{"stiching_attribute_value": "Back", "quantity": 1, "category": "Body"},
		],
		"cutting_cloths_json": {
			"items": [
				{"Panel": "Front", "Colour": "Black", "Cloth": "MAIN"},
				{"Panel": "Back", "Colour": "Navy", "Cloth": "MAIN"},
			]
		},
		"cloth_detail": [{"name1": "MAIN", "cloth": "Jersey", "required_gsm": 180}],
		"item_bom": [{"name": "bom-1", "item": "Label", "qty_of_product": 1, "qty_of_bom_item": 1}],
		"ipd_processes": [{"process_name": "Printing", "in_stage": "Cut"}],
		"emblishment_details_json": {"Printing": ["Front"]},
		**values,
	}
	payload = {
		"values": base,
		"context": {"attributes": [{"attribute": "Size", "values": SIZES}], "bom_mappings": {}},
	}
	return build_summary(payload, {"name": "IPD-TEST"})


def section(result, key):
	return next(entry["data"] for entry in result["sections"] if entry["key"] == key)


def texts(result, section_key=None):
	return [entry["text"] for entry in result["warnings"] if section_key in (None, entry["section"])]


def row_view(row):
	return (row["values"], row["colours"], row["size_label"], row["weight"])


class TestIpdApprovalSummary(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_sections_follow_the_review_order(self):
		result = summary(cutting_items_json=grid(["Panel"], []))
		self.assertEqual([entry["key"] for entry in result["sections"]], list(SECTION_LABELS))
		self.assertEqual(result["sections"][2]["label"], "Piece weight")

	def test_part_basis_keeps_one_row_per_part(self):
		weights = grid(
			["Part"],
			[{"Part": "Top", "Dia": "30", "Weight": 0.1}, {"Part": "Bottom", "Dia": "30", "Weight": 0.1}],
		)
		weight = section(summary(cutting_items_json=weights), "weight")
		self.assertEqual(weight["basis"], ["Part"])
		self.assertEqual(weight["columns"], ["Part"])
		self.assertEqual([row["values"] for row in weight["rows"]], [{"Part": "Top"}, {"Part": "Bottom"}])

	def test_panel_basis(self):
		weights = grid(["Panel"], [{"Panel": "Front", "Weight": 0.2}, {"Panel": "Back", "Weight": 0.18}])
		result = summary(cutting_items_json=weights)
		weight = section(result, "weight")
		self.assertEqual((weight["basis"], weight["source_rows"], len(weight["rows"])), (["Panel"], 2, 2))
		self.assertEqual(result["key_numbers"]["piece_weight"], {"min": 0.38, "max": 0.38})
		self.assertEqual(texts(result, "weight"), [])

	def test_part_colour_panel_merges_identical_colours(self):
		items = [
			{"Part": "Top", "Colour": colour, "Panel": "Front", "Dia": "36", "Weight": 0.029}
			for colour in ("Black", "Navy")
		] + [{"Part": "Top", "Colour": "Red", "Panel": "Front", "Dia": "36", "Weight": 0.03}]
		weight = section(summary(cutting_items_json=grid(["Part", "Colour", "Panel"], items)), "weight")
		self.assertEqual(weight["columns"], ["Part", "Panel", "Colour"])
		self.assertEqual(
			[row_view(row) for row in weight["rows"]],
			[
				({"Part": "Top", "Panel": "Front"}, ["Black", "Navy"], "", 0.029),
				({"Part": "Top", "Panel": "Front"}, ["Red"], "", 0.03),
			],
		)

	def test_size_panel_colour_merges_sizes_and_flags_outliers_inline(self):
		weights = {"Black": 0.04, "Navy": 0.04, "Ming": 0.041, "Maroon": 0.08}
		items = [
			{"Size": size, "Panel": "Front", "Colour": colour, "Dia": "32", "Weight": weight}
			for size in reversed(SIZES)
			for colour, weight in weights.items()
		]
		result = summary(
			cutting_items_json=grid(["Size", "Panel", "Colour"], items), stiching_item_details=FRONT_ONLY
		)
		weight = section(result, "weight")
		self.assertEqual(weight["columns"], ["Panel", "Colour", "Size"])
		self.assertEqual(
			[(*row_view(row), row["outlier_median"]) for row in weight["rows"]],
			[
				({"Panel": "Front"}, ["Black", "Navy"], "S – XL", 0.04, None),
				({"Panel": "Front"}, ["Ming"], "S – XL", 0.041, None),
				({"Panel": "Front"}, ["Maroon"], "S – XL", 0.08, 0.041),
			],
		)
		self.assertEqual(
			texts(result, "weight"),
			[
				"Maroon weight differs from the other colours by more than 50% in 4 size rows. Check the entry."
			],
		)

	def test_size_gaps_split_ranges(self):
		items = [
			{"Size": size, "Panel": "Front", "Weight": weight}
			for size, weight in (("S", 0.1), ("M", 0.1), ("L", 0.2), ("XL", 0.1))
		]
		weight = section(summary(cutting_items_json=grid(["Size", "Panel"], items)), "weight")
		self.assertEqual([row["size_label"] for row in weight["rows"]], ["S – M", "L", "XL"])

	def test_few_outliers_name_their_row(self):
		items = [
			{"Size": "S", "Panel": "Front", "Colour": colour, "Weight": weight}
			for colour, weight in (("Black", 0.04), ("Navy", 0.04), ("Red", 0.1))
		]
		result = summary(
			cutting_items_json=grid(["Size", "Panel", "Colour"], items), stiching_item_details=FRONT_ONLY
		)
		self.assertEqual(
			texts(result, "weight"),
			["Front · S: Red weight differs from the other colours by more than 50% (median 0.04 kg)."],
		)

	def test_unmapped_cut_stage_process_and_unknown_panels(self):
		result = summary(
			cutting_items_json=grid(
				["Panel"], [{"Panel": "Front", "Weight": 0.1}, {"Panel": "Back", "Weight": 0.1}]
			),
			ipd_processes=[
				{"process_name": "Fusing", "in_stage": "Cut"},
				{"process_name": "Ironing", "in_stage": "Piece"},
			],
			emblishment_details_json={"Printing": ["Sleeve"]},
		)
		self.assertEqual(
			texts(result, "embellishment"),
			[
				"Printing is set on panels but missing from the process list.",
				"Printing uses unknown panels: Sleeve.",
				"Fusing runs at Cut stage but is not mapped to any panel.",
			],
		)

	def test_missing_data_warnings(self):
		result = summary(
			cutting_items_json=grid(["Panel"], [{"Panel": "Front", "Weight": 0}]),
			cutting_cloths_json={"items": [{"Panel": "Front", "Colour": "Black", "Cloth": "MAIN"}]},
			cloth_detail=[{"name1": "MAIN", "cloth": "Jersey"}],
			item_bom=[],
			accessory_clothtype_json={"Rib": "Top"},
			cloth_accessory_json={"attributes": ["Accessory", "Dia", "Weight"], "items": []},
		)
		self.assertEqual(
			texts(result),
			[
				"Panels without weight: Back.",
				"1 weight cell(s) are blank or zero.",
				"Colours with no cloth mapping: Navy.",
				"Panels with no cloth: Back.",
				"Cloth MAIN has no required GSM.",
				"No accessories (Item BOM is empty).",
				"Rib has no weight row.",
			],
		)

	def test_varying_bom_row_without_mapping_rows(self):
		result = summary(
			cutting_items_json=grid(
				["Panel"], [{"Panel": "Front", "Weight": 0.1}, {"Panel": "Back", "Weight": 0.1}]
			),
			item_bom=[
				{"name": "bom-1", "item": "Label", "qty_of_product": 1, "qty_of_bom_item": 0},
				{
					"name": "bom-2",
					"item": "Tag",
					"qty_of_product": 1,
					"qty_of_bom_item": 1,
					"based_on_attribute_mapping": 1,
				},
			],
		)
		self.assertEqual(
			texts(result, "accessories"),
			["Label has zero quantity.", "Tag is attribute-mapped but the mapping has no rows."],
		)

	def test_attributes_list_the_ipd_colours(self):
		result = summary(cutting_items_json=grid(["Panel"], []))
		self.assertEqual(result["attributes"]["colours"], ["Black", "Navy"])

	def test_endpoint_reads_a_stored_ipd(self):
		result = workspace.get_ipd_approval_summary(SAMPLES["standard"])
		self.assertEqual(result["header"]["name"], SAMPLES["standard"])
		self.assertEqual([entry["key"] for entry in result["sections"]], list(SECTION_LABELS))
		self.assertTrue(result["header"]["created_by"])

	def test_endpoint_needs_read_permission(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			workspace.get_ipd_approval_summary(SAMPLES["standard"])
