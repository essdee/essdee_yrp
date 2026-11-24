from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.finishing import alternative_transfers
from essdee_yrp.finishing.status import compute_received_status
from essdee_yrp.planning.dashboard.ladder import get_balance
from essdee_yrp.planning.dashboard.lot_metrics import LotMetrics
from essdee_yrp.planning.dashboard.set_quantities import SetQuantities

SQL = "essdee_yrp.finishing.alternative_transfers.frappe.db.sql"
ROWS = [
	("LOT-1", "LOT-1-1", "ALT", "WO-9", 10, "ALT-Red-S", 30),
	("LOT-1", "LOT-1-1", "ALT", "WO-9", 10, "ALT-Red-M", 10),
	("LOT-1", "LOT-1-2", "ALT2", "WO-10", 0, "ALT2-Red-S", 5),
]


class TestAlternativeTransfers(TestCase):
	@patch(SQL, return_value=ROWS)
	def test_one_row_per_alternative_lot_with_pieces_and_boxes(self, sql):
		result = alternative_transfers.get_alternative_transfers(["LOT-1", "LOT-1", None])

		self.assertEqual(sql.call_args_list[0].args[1], {"lots": ("LOT-1",)})
		self.assertEqual(
			result["LOT-1"],
			[
				{"lot": "LOT-1-1", "item": "ALT", "work_order": "WO-9", "quantity": 40.0, "boxes": 4.0},
				{"lot": "LOT-1-2", "item": "ALT2", "work_order": "WO-10", "quantity": 5.0, "boxes": None},
			],
		)

	@patch(SQL, return_value=ROWS)
	def test_per_variant_split(self, _sql):
		rows = alternative_transfers.get_alternative_transfers(["LOT-1"], per_variant=True)["LOT-1"]

		self.assertEqual(rows[0]["variants"], {"ALT-Red-S": 30.0, "ALT-Red-M": 10.0})

	@patch(SQL, return_value=ROWS)
	def test_quantities_sum_every_alternative_lot(self, _sql):
		self.assertEqual(alternative_transfers.get_alternative_quantities(["LOT-1"]), {"LOT-1": 45.0})

	@patch(SQL)
	def test_no_lots_runs_no_query(self, sql):
		self.assertEqual(alternative_transfers.get_alternative_transfers([None]), {})
		sql.assert_not_called()


class TestTransferredQuantities(TestCase):
	"""Alternative variants map to the source row with the same attributes and set combination."""

	ATTRIBUTES = {
		"SRC-Red-S": {"Colour": "Red", "Size": "S"},
		"SRC-Red-M": {"Colour": "Red", "Size": "M"},
		"ALT-Red-S": {"Colour": "Red", "Size": "S"},
		"ALT-Blue-S": {"Colour": "Blue", "Size": "S"},
	}
	RED = (("major_colour", "Red"),)
	SOURCE_KEYS = [("SRC-Red-S", RED), ("SRC-Red-M", RED)]

	def transferred(self, rows):
		with (
			patch(SQL, return_value=[frappe._dict(row) for row in rows]),
			patch(
				"essdee_yrp.finishing.alternative_transfers.get_variant_attr_details",
				side_effect=self.ATTRIBUTES.get,
			),
		):
			return alternative_transfers.get_transferred_quantities("LOT-1", self.SOURCE_KEYS)

	def test_quantities_sum_per_source_row(self):
		rows = [
			{"item_variant": "ALT-Red-S", "set_combination": '{"major_colour": "Red"}', "quantity": 30},
			{"item_variant": "ALT-Red-S", "set_combination": '{\n "major_colour": "Red"\n}', "quantity": 5},
		]
		self.assertEqual(self.transferred(rows), {("SRC-Red-S", self.RED): 35.0})

	def test_unmatched_alternative_variant_fails_loudly(self):
		rows = [{"item_variant": "ALT-Blue-S", "set_combination": '{"major_colour": "Blue"}', "quantity": 1}]
		with self.assertRaises(frappe.ValidationError):
			self.transferred(rows)


class TestFinishingPlanStatusCountsAlternative(TestCase):
	"""Lot 100, 55 dispatched, 40 moved to an alternative lot: 95 done."""

	def status(self, moved):
		settings = frappe._dict(partial_received_percentage=50, partially_dispatched_percentage=90)
		doc = frappe._dict(lot="LOT-1", finishing_plan_details=[])
		with (
			patch("essdee_yrp.finishing.status.get_finishing_plan_total_cutting", return_value=100),
			patch(
				"essdee_yrp.finishing.status.get_finishing_dispatch_totals",
				return_value=frappe._dict(total_dispatched_pieces=55),
			),
			patch("essdee_yrp.finishing.status.frappe.get_cached_doc", return_value=settings),
			patch("essdee_yrp.finishing.status.get_alternative_quantities", return_value={"LOT-1": moved}),
		):
			return compute_received_status(doc)

	def test_moved_pieces_count_as_dispatched(self):
		self.assertEqual(self.status(40), "Dispatched")

	def test_without_alternative_only_dispatch_counts(self):
		self.assertEqual(self.status(0), "Partially Dispatched")


class TestLotSummaryCountsAlternative(TestCase):
	def test_balance_and_status_include_moved_pieces(self):
		metrics = LotMetrics([{"name": "LOT-1", "item": "SHIRT"}], sewing_processes=[])
		metrics.__dict__.update(
			orders=[],
			order_quantities={"LOT-1": (60, 100)},
			cutting_statuses={},
			lay_sheets={},
			cutting_delivered=set(),
			fabric_routes={},
			purchase_lines={},
			dispatch={"LOT-1": 55},
			sets=SetQuantities({}, []),
			item_totals={"WO-CUT": {"planned": 100, "delivered": 100, "received": 100}},
			alternatives={"LOT-1": [{"lot": "LOT-1-1", "item": "ALT", "quantity": 40.0, "boxes": 4.0}]},
		)
		metrics.__dict__["orders_by_lot"] = {
			"LOT-1": [
				{"name": "WO-CUT", "process_name": "Cutting", "is_rework": 0, "includes_packing": 0},
				{"name": "WO-1", "process_name": "Packing", "is_rework": 0, "includes_packing": 1},
			]
		}

		summary = metrics.get_summary("LOT-1")

		self.assertEqual(summary["status"], "Dispatched")
		self.assertEqual(summary["to_alternative"], 40)
		self.assertEqual(summary["cut"], 100)
		self.assertEqual(get_balance(summary["cut"], summary["dispatch"], summary["to_alternative"]), 5)
		self.assertEqual(summary["alternatives"][0]["lot"], "LOT-1-1")
