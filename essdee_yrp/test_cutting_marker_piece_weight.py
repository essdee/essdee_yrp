import json
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.cutting.marker_piece_weight import MarkerPieceWeightError, get_marker_piece_weight
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_marker.sd_yrp_cutting_marker import (
	SDYRPCuttingMarker,
	preview_marker_piece_weight,
)

MARKER_MODULE = "essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_marker.sd_yrp_cutting_marker"
PANELS = [("Front", 1, "Top"), ("Back", 1, "Top"), ("Sleeve", 2, "Top"), ("Leg", 2, "Bottom")]


def make_ipd(attributes, items, is_set_item=0):
	return frappe._dict(
		name="IPD-1",
		cutting_attributes=[frappe._dict(attribute=attribute) for attribute in attributes],
		cutting_items_json=json.dumps({"attributes": [*attributes, "Dia", "Weight"], "items": items}),
		primary_item_attribute="Size",
		stiching_attribute="Panel",
		set_item_attribute="Part",
		is_set_item=is_set_item,
		stiching_item_details=[
			frappe._dict(stiching_attribute_value=panel, quantity=quantity, set_item_attribute_value=part)
			for panel, quantity, part in PANELS
		],
	)


def machine_ratios(panels, **ratios):
	return [
		{"size": size, "panel": panel, "ratio": ratio} for size, ratio in ratios.items() for panel in panels
	]


class TestMarkerPieceWeight(TestCase):
	def test_panel_weights_use_panel_quantity(self):
		ipd = make_ipd(["Panel"], [{"Panel": "Front", "Weight": 0.1}, {"Panel": "Sleeve", "Weight": 0.04}])
		weight = get_marker_piece_weight(ipd, ["Front", "Sleeve"], machine_ratios(["Front", "Sleeve"], M=1))
		self.assertAlmostEqual(weight, 0.18)

	def test_size_weights_follow_marker_ratios(self):
		items = [
			{"Size": "S", "Panel": "Front", "Weight": 0.1},
			{"Size": "L", "Panel": "Front", "Weight": 0.2},
		]
		ipd = make_ipd(["Size", "Panel"], items)
		self.assertAlmostEqual(
			get_marker_piece_weight(ipd, ["Front"], machine_ratios(["Front"], S=1, L=3)), 0.175
		)
		self.assertAlmostEqual(
			get_marker_piece_weight(ipd, ["Front"], machine_ratios(["Front"], S=0, L=0)), 0.15
		)

	def test_manual_ratios_apply_per_panel(self):
		items = [
			{"Size": size, "Panel": panel, "Weight": weight}
			for size, panel, weight in [
				("S", "Front", 0.1),
				("L", "Front", 0.2),
				("S", "Back", 0.1),
				("L", "Back", 0.2),
			]
		]
		ratios = [
			{"size": "S", "panel": "Front", "ratio": 1},
			{"size": "L", "panel": "Front", "ratio": 0},
			{"size": "S", "panel": "Back", "ratio": 0},
			{"size": "L", "panel": "Back", "ratio": 1},
		]
		self.assertAlmostEqual(
			get_marker_piece_weight(make_ipd(["Size", "Panel"], items), ["Front", "Back"], ratios), 0.3
		)

	def test_colour_and_dia_weights_are_averaged(self):
		items = [
			{"Panel": "Front", "Colour": "Red", "Dia": "30", "Weight": 0.1},
			{"Panel": "Front", "Colour": "Navy", "Dia": "32", "Weight": 0.12},
		]
		self.assertAlmostEqual(
			get_marker_piece_weight(
				make_ipd(["Panel", "Colour"], items), ["Front"], machine_ratios(["Front"], M=1)
			),
			0.11,
		)

	def test_part_weight_is_split_across_selected_pieces(self):
		ipd = make_ipd(
			["Part"], [{"Part": "Top", "Weight": 0.25}, {"Part": "Bottom", "Weight": 0.2}], is_set_item=1
		)
		top = ["Front", "Back", "Sleeve"]
		self.assertEqual(get_marker_piece_weight(ipd, top, machine_ratios(top, M=1)), 0.25)
		self.assertAlmostEqual(
			get_marker_piece_weight(ipd, ["Front", "Back"], machine_ratios(["Front", "Back"], M=1)), 0.125
		)
		self.assertAlmostEqual(
			get_marker_piece_weight(ipd, ["Sleeve", "Leg"], machine_ratios(["Sleeve", "Leg"], M=1)), 0.325
		)

	def test_part_weight_full_selection_keeps_stored_weight(self):
		ipd = make_ipd(["Part"], [{"Part": "Top", "Weight": 0.262}], is_set_item=1)
		ipd.stiching_item_details = [
			frappe._dict(
				stiching_attribute_value=f"P{index}", quantity=quantity, set_item_attribute_value="Top"
			)
			for index, quantity in enumerate([1, 1, 1, 2, 2, 1, 1, 1, 2, 1, 1])
		]
		panels = [f"P{index}" for index in range(11)]
		self.assertEqual(get_marker_piece_weight(ipd, panels, machine_ratios(panels, M=1)), 0.262)

	def test_garment_weight_is_split_across_selected_pieces(self):
		ipd = make_ipd(["Colour"], [{"Colour": "Red", "Weight": 0.3}])
		panels = [panel for panel, *_ in PANELS]
		self.assertEqual(get_marker_piece_weight(ipd, panels, machine_ratios(panels, M=1)), 0.3)
		self.assertAlmostEqual(get_marker_piece_weight(ipd, panels[:3], machine_ratios(panels[:3], M=1)), 0.2)

	def test_unusable_weights_are_blocked(self):
		cases = [
			(make_ipd(["Panel"], []), "has no cutting consumption weights"),
			(make_ipd(["Panel"], [{"Panel": "Back", "Weight": 0.1}]), "no cutting weight for Front"),
			(make_ipd(["Panel"], [{"Panel": "Front", "Weight": 120}]), "looks like grams"),
		]
		for ipd, message in cases:
			with self.subTest(message=message), self.assertRaisesRegex(MarkerPieceWeightError, message):
				get_marker_piece_weight(ipd, ["Front"], machine_ratios(["Front"], M=1))

	def test_missing_size_weight_names_panel_and_size(self):
		ipd = make_ipd(["Size", "Panel"], [{"Size": "S", "Panel": "Front", "Weight": 0.1}])
		with self.assertRaisesRegex(MarkerPieceWeightError, "Front / L"):
			get_marker_piece_weight(ipd, ["Front"], machine_ratios(["Front"], S=1, L=1))


class TestMarkerSaveComputesPieceWeight(TestCase):
	ipd = make_ipd(["Panel"], [{"Panel": "Front", "Weight": 0.1}, {"Panel": "Back", "Weight": 0.1}])

	def save(self, **values):
		doc = frappe._dict(
			{
				"cutting_plan": "CP-1",
				"cutting_order": None,
				"selected_type": "Machine",
				"calculated_parts": "Front,Back",
				"required_piece_weight": 9,
				"marker_details": {"ratio_items": [{"size": "M", "ratio": 1}], "group_items": []},
				**values,
			}
		)
		doc.set = lambda field, rows: doc.update({field: [frappe._dict(row) for row in rows]})
		doc.set_marker_details = lambda: SDYRPCuttingMarker.set_marker_details(doc)
		doc.set_required_piece_weight = lambda: SDYRPCuttingMarker.set_required_piece_weight(doc)
		with (
			patch(f"{MARKER_MODULE}.get_parent_ref", return_value=("SD YRP Cutting Plan", "CP-1")),
			patch(f"{MARKER_MODULE}.validate_parent_status"),
			patch(f"{MARKER_MODULE}.get_parent_context", return_value={"item": "SHIRT"}),
			patch(f"{MARKER_MODULE}.frappe.get_value", return_value="IPD-1"),
			patch(f"{MARKER_MODULE}.frappe.get_cached_doc", return_value=self.ipd),
			patch(
				f"{MARKER_MODULE}.frappe.db.get_single_value",
				side_effect=lambda _doctype, field: {"piece_weight_min": 0.1, "piece_weight_max": 0.5}[field],
			),
		):
			SDYRPCuttingMarker.before_validate(doc)
		return doc

	def test_typed_weight_is_replaced_by_ipd_weight(self):
		doc = self.save()
		self.assertAlmostEqual(doc.required_piece_weight, 0.2)
		self.assertEqual(len(doc.cutting_marker_ratios), 2)

	def test_without_panels_weight_is_cleared(self):
		doc = self.save(calculated_parts="", marker_details=None, cutting_marker_ratios=[])
		self.assertEqual(doc.required_piece_weight, 0)

	def test_cutting_order_marker_is_blocked(self):
		with self.assertRaisesRegex(MarkerPieceWeightError, "Cutting Order"):
			self.save(cutting_plan=None, cutting_order="CO-1")

	def test_settings_range_applies_to_computed_weight(self):
		self.ipd.cutting_items_json = json.dumps(
			{"items": [{"Panel": "Front", "Weight": 0.4}, {"Panel": "Back", "Weight": 0.4}]}
		)
		try:
			with self.assertRaisesRegex(frappe.ValidationError, "outside the allowed range"):
				self.save()
		finally:
			self.ipd.cutting_items_json = json.dumps(
				{"items": [{"Panel": "Front", "Weight": 0.1}, {"Panel": "Back", "Weight": 0.1}]}
			)


class TestPreviewMarkerPieceWeight(TestCase):
	def preview(self, **kwargs):
		parent = frappe._dict(production_detail="IPD-1", check_permission=lambda _perm: None)
		ipd = make_ipd(["Panel"], [{"Panel": "Front", "Weight": 0.1}])
		with (
			patch(
				f"{MARKER_MODULE}._web_parent",
				return_value=(parent, "SD YRP Cutting Plan", "CP-1", "cutting_plan"),
			),
			patch(f"{MARKER_MODULE}.frappe.get_cached_doc", return_value=ipd),
		):
			return preview_marker_piece_weight(cutting_plan="CP-1", **kwargs)

	def test_machine_ratios_apply_to_every_panel(self):
		result = self.preview(
			selected_type="Machine", panels='["Front"]', ratio_items='[{"size": "M", "ratio": 2}]'
		)
		self.assertEqual(result, {"weight": 0.1, "message": ""})

	def test_errors_are_returned_as_messages(self):
		result = self.preview(
			selected_type="Machine", panels='["Back"]', ratio_items='[{"size": "M", "ratio": 1}]'
		)
		self.assertIsNone(result["weight"])
		self.assertIn("no cutting weight for Back", result["message"])
