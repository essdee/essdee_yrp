from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.planning.dashboard import dashboard, tracking
from essdee_yrp.planning.dashboard.production_orders import PPO, get_product_categories

PREFIX = "_TEST-PDCAT-"
ITEMS = {
	f"{PREFIX}TEMPLATE": ("Thermal", None),
	f"{PREFIX}VARIANT": (None, f"{PREFIX}TEMPLATE"),
	f"{PREFIX}OWN": ("Vest", f"{PREFIX}TEMPLATE"),
	f"{PREFIX}NONE": (None, None),
}


def lot(name, ppo, item):
	return {
		"name": name,
		"production_order": ppo,
		"item": item,
		"total_order_quantity": 10,
		"packing_combo": 0,
	}


SUMMARY = {
	"status": "In sewing",
	"status_rank": 500,
	"purchase_split": None,
	"planned": 10,
	"order_cut": 10,
	"cut": 10,
	"stitch": 0,
	"packed": 0,
	"total": 10,
	"dispatch": 0,
	"to_alternative": 0,
	"alternatives": [],
	"balance": 10,
}


class ItemFixtures(TestCase):
	def setUp(self):
		for name, (category, template) in ITEMS.items():
			frappe.db.sql(
				"insert into `tabItem` (name, item_code, item_name, product_category, variant_of) values (%s, %s, %s, %s, %s)",
				(name, name, name, category, template),
			)

	def tearDown(self):
		frappe.db.rollback()


class TestProductCategories(ItemFixtures):
	def test_variant_falls_back_to_template_category(self):
		self.assertEqual(
			get_product_categories([*ITEMS, None, ""]),
			{f"{PREFIX}TEMPLATE": "Thermal", f"{PREFIX}VARIANT": "Thermal", f"{PREFIX}OWN": "Vest"},
		)

	def test_no_items_means_no_query(self):
		with patch("frappe.db.sql") as sql:
			self.assertEqual(get_product_categories([]), {})
		sql.assert_not_called()


class TestDashboardCategory(ItemFixtures):
	def test_every_lot_row_carries_its_item_category(self):
		lots = [lot("L-1", "PPO-1", f"{PREFIX}VARIANT"), lot("L-2", "PPO-1", f"{PREFIX}NONE")]
		metrics = MagicMock(get_summary=lambda name: SUMMARY)
		with (
			patch.object(
				dashboard.frappe, "get_list", return_value=[{"name": "PPO-1", "delivery_date": None}]
			),
			patch.object(dashboard, "get_lots", return_value=lots),
			patch.object(dashboard, "get_ppo_details", return_value={"PPO-1": {"delivery": None}}),
			patch.object(dashboard, "get_lots_with_work_orders", return_value={"L-1"}),
			patch.object(dashboard, "get_sewing_processes", return_value=[]),
			patch.object(dashboard, "LotMetrics", return_value=metrics),
		):
			rows = dashboard.get_dashboard_data()["lots"]
		self.assertEqual(
			{row["lot"]: row["product_category"] for row in rows}, {"L-1": "Thermal", "L-2": None}
		)


class TestTrackingCategory(ItemFixtures):
	LOTS = [
		lot("L-1", "PPO-1", f"{PREFIX}VARIANT"),
		lot("L-2", "PPO-1", f"{PREFIX}OWN"),
		lot("L-3", "PPO-2", f"{PREFIX}NONE"),
	]

	def patched(self):
		metrics = MagicMock(get_summary=lambda name: SUMMARY, purchase_totals={})
		metrics.get_purchase_summary.return_value = None
		real_get_list = frappe.get_list

		def get_list(doctype, filters=None, **kwargs):
			if doctype != PPO:
				return real_get_list(doctype, filters=filters, **kwargs)
			names = ["PPO-1", "PPO-2"]
			if "name" in (filters or {}):
				names = [name for name in names if name in filters["name"][1]]
			if kwargs.get("pluck"):
				return names
			return [{"name": name, "status": "Open", "delivery_date": None} for name in names]

		def get_lots(ppos):
			return [row for row in self.LOTS if row["production_order"] in ppos]

		return (
			patch.object(tracking.frappe, "get_list", side_effect=get_list),
			patch.object(tracking, "get_lots", side_effect=get_lots),
			patch.object(tracking, "get_lots_with_work_orders", return_value={"L-1", "L-2", "L-3"}),
			patch.object(tracking, "LotMetrics", return_value=metrics),
			patch.object(tracking, "LotProcesses", return_value=MagicMock(get_processes=lambda name: [])),
			patch.object(
				tracking,
				"get_ppo_items",
				return_value={"PPO-1": {"item": "", "item_name": ""}, "PPO-2": {"item": "", "item_name": ""}},
			),
			patch.object(
				tracking,
				"get_ppo_details",
				side_effect=lambda orders, lots: {row["name"]: {"delivery": None} for row in orders},
			),
			patch.object(
				tracking, "authorize_filter_values", side_effect=lambda doctype, values: values or []
			),
		)

	def run_patched(self, call):
		patches = self.patched()
		for item in patches:
			item.start()
		try:
			return call()
		finally:
			for item in reversed(patches):
				item.stop()

	def test_options_carry_lot_and_ppo_categories(self):
		result = self.run_patched(tracking.get_tracking_options)
		self.assertEqual(
			{row["name"]: row["product_category"] for row in result["lots"]},
			{"L-1": "Thermal", "L-2": "Vest", "L-3": None},
		)
		self.assertEqual(
			{row["name"]: row["product_categories"] for row in result["ppos"]},
			{"PPO-1": ["Thermal", "Vest"], "PPO-2": []},
		)

	def test_a_category_alone_scopes_tracking_to_its_lots(self):
		result = self.run_patched(lambda: tracking.get_tracking_data([], [], ["Thermal"]))
		self.assertEqual([row["lot"] for row in result["lots"]], ["L-1"])
		self.assertEqual(list(result["ppos"]), ["PPO-1"])
		self.assertEqual(result["lots"][0]["product_category"], "Thermal")
		self.assertEqual(
			{row["lot"]: row["product_category"] for row in result["ppos"]["PPO-1"]["lots"]},
			{"L-1": "Thermal", "L-2": "Vest"},
		)

	def test_category_narrows_selected_ppos(self):
		result = self.run_patched(lambda: tracking.get_tracking_data(["PPO-1", "PPO-2"], [], ["Vest"]))
		self.assertEqual([row["lot"] for row in result["lots"]], ["L-2"])

	def test_tracking_still_needs_a_scope(self):
		with self.assertRaises(frappe.ValidationError):
			self.run_patched(lambda: tracking.get_tracking_data([], [], []))

	def test_category_values_must_be_names(self):
		with self.assertRaises(frappe.ValidationError):
			self.run_patched(lambda: tracking.get_tracking_data([], [], [{"name": "Thermal"}]))
