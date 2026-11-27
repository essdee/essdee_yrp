from unittest import TestCase
from unittest.mock import MagicMock, patch

from essdee_yrp.planning.dashboard import dashboard, ladder, production_orders

LOT = {"name": "L-1", "production_order": "PPO-1", "item": "ITEM-A", "total_order_quantity": 10}
SUMMARY = {
	"status": "In sewing",
	"status_rank": 600,
	"purchase_split": None,
	"qty": 10,
	"is_set": False,
	**dict.fromkeys(dashboard.ZERO_FIGURES, 0.0),
}
PPOS = {
	"PPO-1": {
		"delivery": "2026-10-01",
		"item": "ITEM-A",
		"item_name": "A",
		"boxes": 1,
		"pieces": 10,
		"lot_shares": {"L-1": 10},
	},
	"PPO-3": {
		"delivery": "2026-10-20",
		"item": "ITEM-C",
		"item_name": "C",
		"boxes": 1,
		"pieces": 5,
		"lot_shares": {},
	},
	"PPO-2": {
		"delivery": "2026-10-15",
		"item": "ITEM-V",
		"item_name": "Casual Designer Vest - 7",
		"boxes": 4000,
		"pieces": None,
		"lot_shares": {},
	},
}


LINKED = {"PPO-1": {"L-1": "Open"}, "PPO-3": {"L-3/1": "Closed", "L-3/2": "Close"}}


class TestLotNotLinked(TestCase):
	def get_rows(self):
		orders = [{"name": name, "delivery_date": None} for name in ("PPO-1", "PPO-2", "PPO-3")]
		with (
			patch.object(dashboard.frappe, "get_list", return_value=orders),
			patch.object(dashboard, "get_lots", return_value=[LOT]),
			patch.object(dashboard, "get_linked_lots", return_value=LINKED),
			patch.object(dashboard, "get_lots_with_work_orders", return_value={"L-1"}),
			patch.object(dashboard, "get_sewing_processes", return_value=[]),
			patch.object(dashboard, "LotMetrics", return_value=MagicMock(get_summary=lambda name: SUMMARY)),
			patch.object(dashboard, "get_ppo_details", return_value=PPOS),
			patch.object(dashboard, "get_product_categories", return_value={"ITEM-V": "Vest"}),
		):
			return dashboard.get_dashboard_data()["lots"]

	def test_open_ppo_without_any_lot_is_a_lot_not_linked_row(self):
		rows = self.get_rows()
		self.assertEqual([row["lot"] for row in rows], ["L-1", None, None])
		row = next(row for row in rows if row["ppo"] == "PPO-2")
		self.assertEqual(row["ppo"], "PPO-2")
		self.assertEqual(row["status"], ladder.LOT_NOT_LINKED)
		self.assertEqual(row["item"], "ITEM-V")
		self.assertIsNone(row["ppo_qty"])
		self.assertEqual(row["delivery"], "2026-10-15")
		self.assertEqual(row["product_category"], "Vest")
		self.assertFalse(row["has_work_order"])

	def test_lot_not_linked_ranks_before_po_created(self):
		rank = ladder.get_status_rank
		self.assertLess(rank(ladder.LOT_NOT_LINKED, 0), rank(ladder.PO_CREATED, 0))
		self.assertEqual(self.get_rows()[1]["status_rank"], rank(ladder.LOT_NOT_LINKED, 0))

	def test_open_ppo_whose_lots_are_all_closed_is_a_lots_closed_row(self):
		row = next(row for row in self.get_rows() if row["ppo"] == "PPO-3")
		self.assertEqual(row["status"], ladder.LOTS_CLOSED)
		self.assertIsNone(row["lot"])
		self.assertEqual(row["closed_lots"], "L-3/1 (Closed), L-3/2 (Close)")
		self.assertEqual(row["ppo_qty"], 5)
		self.assertEqual(row["delivery"], "2026-10-20")
		self.assertFalse(row["has_work_order"])

	def test_lots_closed_ranks_between_lot_not_linked_and_po_created(self):
		rank = ladder.get_status_rank
		self.assertLess(rank(ladder.LOT_NOT_LINKED, 0), rank(ladder.LOTS_CLOSED, 0))
		self.assertLess(rank(ladder.LOTS_CLOSED, 0), rank(ladder.PO_CREATED, 0))

	def test_ppo_with_an_open_lot_gets_only_its_lot_row(self):
		self.assertEqual([row["lot"] for row in self.get_rows() if row["ppo"] == "PPO-1"], ["L-1"])


class TestLinkedLots(TestCase):
	def test_any_lot_status_and_ordered_detail_rows_count_as_linked(self):
		calls = []

		def get_all(doctype, filters, fields, distinct=False, limit_page_length=None):
			calls.append((doctype, filters))
			if doctype == "YRP Production Ordered Detail":
				return [{"parent": "PPO-2", "lot": "L-2"}]
			if "name" in filters:
				return [{"name": "L-2", "status": "Closed", "production_order": "PPO-9"}]
			return [{"name": "L-1", "status": "Closed", "production_order": "PPO-1"}]

		with patch.object(production_orders.frappe, "get_all", side_effect=get_all):
			linked = production_orders.get_linked_lots(["PPO-1", "PPO-2", "PPO-3"])
		self.assertEqual(linked, {"PPO-1": {"L-1": "Closed"}, "PPO-2": {"L-2": "Closed"}})
		self.assertNotIn("status", calls[0][1])
		self.assertEqual(calls[1][1]["parenttype"], production_orders.PPO)
