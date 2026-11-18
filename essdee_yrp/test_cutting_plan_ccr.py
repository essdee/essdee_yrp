from unittest import TestCase
from unittest.mock import patch

from frappe import _dict

from essdee_yrp.cutting.ccr import build_cutting_plan_ccr, group_cloth_by_type, serialize_size_groups


def completed_json():
	return {
		"pack_attr": "Colour",
		"is_set_item": 1,
		"set_item_attr": "Part",
		"primary_attribute_values": ["S", "M"],
		"items": [
			{
				"attributes": {"Colour": "Red", "Part": "Top"},
				"values": {"S": 2, "M": 0},
				"is_set_item": 1,
				"set_attr": "Part",
				"major_attr_value": "Top",
			},
			{
				"attributes": {"Colour": "Navy", "Part": "Bottom"},
				"values": {"S": 1, "M": 3},
				"is_set_item": 1,
				"set_attr": "Part",
				"major_attr_value": "Top",
				"item_keys": {"major_colour": "Red"},
			},
			{"attributes": {"Colour": "Empty", "Part": "Top"}, "values": {"S": 0, "M": 0}},
		],
	}


class TestCuttingPlanCcr(TestCase):
	def test_completed_rows_drop_empty_rows_and_label_minor_set_parts(self):
		groups = serialize_size_groups(completed_json(), "completed", "V3")

		self.assertEqual(len(groups), 1)
		self.assertEqual(groups[0]["set_item_attr"], "Part")
		self.assertEqual(groups[0]["primary_values"], ["S", "M"])
		self.assertEqual(
			[(row["label"], row["set_value"]) for row in groups[0]["rows"]],
			[("Red", "Top"), ("Navy (Red)", "Bottom")],
		)

	def test_v1_rows_keep_plain_labels_and_missing_json_is_empty(self):
		groups = serialize_size_groups(completed_json(), "completed", "V1")

		self.assertEqual([row["label"] for row in groups[0]["rows"]], ["Red", "Navy"])
		self.assertEqual(serialize_size_groups(None, "completed", "V1"), [])

	def test_excess_rows_keep_panel_counts(self):
		excess = {
			"pack_attr": "Colour",
			"primary_attribute_values": ["S"],
			"items": [
				{"attributes": {"Colour": "Red"}, "values": {"S": {"Front": 2, "Back": 0}}},
				{"attributes": {"Colour": "Blue"}, "values": {"S": {"Front": 0}}},
			],
		}

		groups = serialize_size_groups(excess, "incompleted", "V1")

		self.assertEqual(
			groups[0]["rows"], [{"label": "Red", "set_value": None, "values": {"S": {"Front": 2, "Back": 0}}}]
		)

	def test_cloth_rows_group_by_cloth_type_in_first_seen_order(self):
		rows = [{"cloth_type": "Body"}, {"cloth_type": "Rib"}, {"cloth_type": "Body"}]

		groups = group_cloth_by_type(rows)

		self.assertEqual(
			[(group["cloth_type"], len(group["rows"])) for group in groups], [("Body", 2), ("Rib", 1)]
		)

	def test_plan_without_label_printed_laysheets_still_returns_sections(self):
		plan = _dict(
			name="CP-1",
			version="V1",
			cutting_plan_accessory_details=[],
			cutting_plan_cloth_details=[],
			completed_items_json=None,
			incomplete_items_json=None,
		)
		with (
			patch("essdee_yrp.cutting.ccr.build_ccr", return_value=None),
			patch("essdee_yrp.cutting.ccr.fetch_cloth_details", return_value=[]),
		):
			data = build_cutting_plan_ccr(plan)

		self.assertEqual(
			data,
			{
				"marker_groups": [],
				"accessories": [],
				"print_panels": [],
				"recuts": [],
				"cloth_groups": [],
				"completed": [],
				"excess": [],
			},
		)
