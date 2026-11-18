import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from essdee_yrp.cut_panel_store.movement_workspace import (
	create_movement_transaction,
	get_movement_linked_documents,
)
from essdee_yrp.cutting.movement import (
	build_delivery_challan_defaults,
	build_stock_entry_defaults,
	get_grouped_movement_rows,
)

MOVEMENT = "CPM-2608-00220"
WORK_ORDER = "WO-2627-00857"
TO_WAREHOUSE = "S-0163"
DELIVERY_CHALLAN = "yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan"
LEDGER = "essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_bundle_movement_ledger.sd_yrp_cut_bundle_movement_ledger"


def insert_submitted_work_order_row(doctype, parentfield, values):
	frappe.get_doc(
		{
			"doctype": doctype,
			"parent": WORK_ORDER,
			"parenttype": "YRP Work Order",
			"parentfield": parentfield,
			"docstatus": 1,
			**values,
		}
	).insert(ignore_permissions=True)


class TestDraftRootsDoNotBlockCutPanelMovement(IntegrationTestCase):
	"""Draft Stock Entry/DC/GRN never block; the first submitted one owns the CPM."""

	def setUp(self):
		frappe.set_user("Administrator")
		if not frappe.db.exists(
			"SD YRP Cut Panel Movement",
			{"name": MOVEMENT, "docstatus": 1, "against_id": ["is", "not set"]},
		):
			self.skipTest(f"Unlinked Cut Panel Movement oracle {MOVEMENT} is unavailable")
		if not frappe.db.exists(
			"YRP Work Order", {"name": WORK_ORDER, "docstatus": 1, "open_status": ["!=", "Close"]}
		):
			self.skipTest(f"Open Work Order oracle {WORK_ORDER} is unavailable")
		frappe.db.savepoint("draft_roots")
		self.addCleanup(frappe.db.rollback, save_point="draft_roots")
		self.prepare_work_order()
		# The oracle's stock and bundles are no longer at the source; root ownership is what is under test.
		for target, value in (
			("yrp.stock.stock_ledger._item_allows_negative_stock", True),
			(f"{DELIVERY_CHALLAN}.YRPDeliveryChallan.validate_stock_available", None),
			(f"{LEDGER}.get_cut_bundle_entry", ([], [])),
			(f"{LEDGER}.make_cut_bundle_ledger", None),
		):
			patcher = patch(target, return_value=value)
			patcher.start()
			self.addCleanup(patcher.stop)

	def prepare_work_order(self):
		movement, _ipd, rows = get_grouped_movement_rows(MOVEMENT, "YRP Delivery Challan")
		for index, row in enumerate(rows):
			qty = flt(row["qty"])
			values = {
				"item_variant": row["item_variant"],
				"qty": qty,
				"uom": row["uom"],
				"lot": movement.lot,
				"received_type": row["received_type"],
				"pending_quantity": qty,
				"table_index": index,
				"row_index": index,
				"set_combination": row["set_combination"],
			}
			for doctype, parentfield in (
				("YRP Work Order Deliverables", "deliverables"),
				("YRP Work Order Receivables", "receivables"),
			):
				insert_submitted_work_order_row(doctype, parentfield, values)
		frappe.clear_document_cache("YRP Work Order", WORK_ORDER)

	def draft_delivery_challan(self):
		defaults = build_delivery_challan_defaults(MOVEMENT, WORK_ORDER)
		doc = frappe.new_doc("YRP Delivery Challan")
		for fieldname, value in defaults.items():
			if fieldname not in {"items", "item_details", "correction_items", "correction_item_details"} and doc.meta.get_field(fieldname):
				doc.set(fieldname, value)
		doc.item_details = json.dumps(defaults["item_details"])
		return doc.insert()

	def test_draft_delivery_challan_allows_a_stock_entry_and_submitted_one_blocks_the_rest(self):
		draft_dc = self.draft_delivery_challan()

		actions = get_movement_linked_documents(MOVEMENT)["actions"]
		self.assertTrue(actions["stock_entry"]["eligible"])
		self.assertEqual(actions["stock_entry"]["reason"], "")
		self.assertEqual(build_stock_entry_defaults(MOVEMENT)["cut_panel_movement"], MOVEMENT)
		created = create_movement_transaction(
			MOVEMENT, "stock_entry", {"to_warehouse": TO_WAREHOUSE}, submit=True
		)
		stock_entry = created["record"]["name"]

		self.assertEqual(frappe.db.get_value("YRP Stock Entry", stock_entry, "docstatus"), 1)
		self.assertEqual(frappe.db.get_value("SD YRP Cut Panel Movement", MOVEMENT, "against_id"), stock_entry)
		moved = f"already moved by submitted YRP Stock Entry {stock_entry}"
		draft_dc.reload()
		with self.assertRaisesRegex(frappe.ValidationError, moved):
			draft_dc.submit()
		self.assertEqual(frappe.db.get_value("YRP Delivery Challan", draft_dc.name, "docstatus"), 0)
		with self.assertRaisesRegex(frappe.ValidationError, moved):
			build_delivery_challan_defaults(MOVEMENT, WORK_ORDER)
		actions = get_movement_linked_documents(MOVEMENT)["actions"]
		self.assertFalse(actions["delivery_challan"]["eligible"])
		self.assertIn(stock_entry, actions["delivery_challan"]["reason"])

	def test_any_one_of_two_draft_delivery_challans_can_be_submitted(self):
		first = self.draft_delivery_challan()
		second = self.draft_delivery_challan()

		second.submit()

		self.assertEqual(frappe.db.get_value("SD YRP Cut Panel Movement", MOVEMENT, "against_id"), second.name)
		first.reload()
		with self.assertRaisesRegex(
			frappe.ValidationError, f"already moved by submitted YRP Delivery Challan {second.name}"
		):
			first.submit()
		self.assertEqual(frappe.db.get_value("YRP Delivery Challan", first.name, "docstatus"), 0)
