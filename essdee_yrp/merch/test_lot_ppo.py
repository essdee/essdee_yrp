from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.merch import lot_ppo
from essdee_yrp.merch import lot_workspace as merch_lot_workspace
from essdee_yrp.planning import lot_workspace as planning_lot_workspace

LOT = "SD YRP Lot"
ORDERED = "YRP Production Ordered Detail"
OTHER_USER = "lot-ppo-other@example.com"


def find_unlinkable_lot():
	"""A migrated Lot linked to a PPO with box rows and nothing downstream."""
	rows = frappe.db.sql(
		"""
		SELECT l.name FROM `tabSD YRP Lot` l
		WHERE IFNULL(l.production_order, '') != '' AND IFNULL(l.production_detail, '') != ''
			AND l.is_transferred = 0
			AND EXISTS (SELECT 1 FROM `tabSD YRP Lot Order Item` i WHERE i.parent = l.name)
			AND EXISTS (SELECT 1 FROM `tabYRP Production Ordered Detail` p
				WHERE p.parent = l.production_order AND (p.lot = l.name OR p.reference_name = l.name))
			AND NOT EXISTS (SELECT 1 FROM `tabYRP Work Order` w WHERE w.lot = l.name AND w.docstatus < 2)
			AND NOT EXISTS (SELECT 1 FROM `tabSD YRP Cutting Plan` c WHERE c.lot = l.name AND c.docstatus < 2)
			AND NOT EXISTS (SELECT 1 FROM `tabYRP Stock Ledger Entry` s WHERE s.lot = l.name AND s.is_cancelled = 0)
			AND NOT EXISTS (SELECT 1 FROM `tabSD YRP Time and Action` t
				WHERE t.against = 'SD YRP Lot' AND t.against_id = l.name AND t.status != 'Frozen')
		ORDER BY l.modified DESC LIMIT 1
		"""
	)
	return rows[0][0] if rows else None


def ordered_rows(production_order):
	return sorted(
		frappe.get_all(
			ORDERED,
			filters={"parent": production_order},
			fields=["item_variant", "quantity", "reference_name", "lot"],
		),
		key=lambda row: (row.reference_name or row.lot or "", row.item_variant, row.quantity),
	)


class TestLotPpoUnlink(IntegrationTestCase):
	def setUp(self):
		self.lot_name = find_unlinkable_lot()
		if not self.lot_name:
			self.skipTest("Lot/PPO unlink parity runs after data migration")
		frappe.db.savepoint("lot_ppo_unlink")
		self.addCleanup(frappe.db.rollback, save_point="lot_ppo_unlink")
		self.lot = frappe.get_doc(LOT, self.lot_name)
		self.production_order = self.lot.production_order

	def unlink(self):
		modified = frappe.db.get_value(LOT, self.lot_name, "modified")
		return lot_ppo.unlink_lot_production_order(self.lot_name, str(modified))

	def lot_rows(self):
		return [
			row
			for row in ordered_rows(self.production_order)
			if self.lot_name in (row.reference_name, row.lot)
		]

	def test_assigned_person_merch_manager_and_system_manager_may_unlink(self):
		self.lot.assigned_person = "assigned@example.com"
		cases = (
			("assigned@example.com", [], True),
			(OTHER_USER, ["Merch Manager"], True),
			(OTHER_USER, ["System Manager"], True),
			(OTHER_USER, ["Merchandiser", "Merch User"], False),
		)
		for user, roles, allowed in cases:
			with self.subTest(user=user, roles=roles), patch("frappe.get_roles", return_value=roles):
				self.assertEqual(lot_ppo.can_unlink_ppo(self.lot, user), allowed)

	def test_other_user_is_refused_server_side(self):
		with (
			patch("frappe.get_roles", return_value=["Merchandiser"]),
			patch.dict(frappe.session, {"user": OTHER_USER}),
			self.assertRaises(frappe.PermissionError),
		):
			self.unlink()
		self.assertEqual(frappe.db.get_value(LOT, self.lot_name, "production_order"), self.production_order)

	def test_unlink_clears_ppo_fields_and_box_rows(self):
		self.assertTrue(self.lot_rows())
		self.unlink()
		doc = frappe.get_doc(LOT, self.lot_name)
		for field in (
			"production_order",
			"item",
			"production_detail",
			"uom",
			"packing_uom",
			"pack_out_stage",
		):
			with self.subTest(field=field):
				self.assertFalse(doc.get(field))
		self.assertEqual(doc.items, [])
		self.assertEqual(doc.lot_order_details, [])
		self.assertEqual((doc.total_quantity, doc.total_order_quantity), (0, 0))
		self.assertEqual(self.lot_rows(), [])

	def test_ppo_quantities_match_remove_ppo_and_save_path(self):
		frappe.db.savepoint("remove_and_save")
		self.lot.production_order = ""
		self.lot.item = ""
		self.lot.production_detail = ""
		self.lot.save()
		expected = ordered_rows(self.production_order)
		frappe.db.rollback(save_point="remove_and_save")
		self.assertNotEqual(ordered_rows(self.production_order), expected)

		self.unlink()
		self.assertEqual(ordered_rows(self.production_order), expected)

	def test_downstream_documents_block_unlink(self):
		work_order = frappe.new_doc("YRP Work Order")
		work_order.lot = self.lot_name
		work_order.name = f"LOT-PPO-TEST-{frappe.generate_hash(length=6)}"
		work_order.db_insert()
		with self.assertRaisesRegex(frappe.ValidationError, "Work Order"):
			self.unlink()
		self.assertEqual(frappe.db.get_value(LOT, self.lot_name, "production_order"), self.production_order)

	def test_transferred_lot_and_missing_ppo_block_unlink(self):
		self.assertEqual(lot_ppo.get_unlink_ppo_block(self.lot), "")
		self.lot.is_transferred = 1
		self.assertIn("transferred", lot_ppo.get_unlink_ppo_block(self.lot))
		self.lot.is_transferred = 0
		self.lot.production_order = ""
		self.assertIn("No Production Order", lot_ppo.get_unlink_ppo_block(self.lot))

	def test_merch_workspace_exposes_unlink_command(self):
		capability = merch_lot_workspace.get_lot_capabilities(self.lot)["unlink_ppo"]
		self.assertTrue(capability["visible"])
		self.assertTrue(capability["allowed"])
		merch_lot_workspace.execute_merch_lot_command(
			self.lot_name, "unlink_ppo", expected_modified=str(self.lot.modified)
		)
		self.assertFalse(frappe.db.get_value(LOT, self.lot_name, "production_order"))

	def test_planning_workspace_exposes_unlink_capability(self):
		capability = planning_lot_workspace.get_lot_workspace(self.lot_name)["unlink_ppo"]
		self.assertEqual((capability["visible"], capability["allowed"]), (True, True))
		with patch("frappe.get_roles", return_value=["Merchandiser"]):
			hidden = planning_lot_workspace.get_lot_workspace(self.lot_name)["unlink_ppo"]
		self.assertFalse(hidden["visible"])
