from unittest import TestCase
from unittest.mock import MagicMock, patch

from essdee_yrp.planning.dashboard import dashboard, ladder

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
	"PPO-2": {
		"delivery": "2026-10-15",
		"item": "ITEM-V",
		"item_name": "Casual Designer Vest - 7",
		"boxes": 4000,
		"pieces": None,
		"lot_shares": {},
	},
}


class TestLotNotLinked(TestCase):
	def get_rows(self):
		orders = [{"name": "PPO-1", "delivery_date": None}, {"name": "PPO-2", "delivery_date": None}]
		with (
			patch.object(dashboard.frappe, "get_list", return_value=orders),
			patch.object(dashboard, "get_lots", return_value=[LOT]),
			patch.object(dashboard, "get_lots_with_work_orders", return_value={"L-1"}),
			patch.object(dashboard, "get_sewing_processes", return_value=[]),
			patch.object(dashboard, "LotMetrics", return_value=MagicMock(get_summary=lambda name: SUMMARY)),
			patch.object(dashboard, "get_ppo_details", return_value=PPOS),
			patch.object(dashboard, "get_product_categories", return_value={"ITEM-V": "Vest"}),
		):
			return dashboard.get_dashboard_data()["lots"]

	def test_open_ppo_without_open_lot_is_a_lot_not_linked_row(self):
		rows = self.get_rows()
		self.assertEqual([row["lot"] for row in rows], ["L-1", None])
		row = rows[1]
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
