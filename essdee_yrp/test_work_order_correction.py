from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from yrp.stock.save_stock_items import group_items_for_ui

from essdee_yrp.work_order_correction import (
	_delivered_correction_rows,
	create_work_order_correction,
	get_work_order_correction_context,
	is_correction_supported,
	write_off_correction_stock,
)


class TestWorkOrderCorrectionHook(TestCase):
	def test_supported_on_fabric_source_and_exact_source_work_orders(self):
		work_order = frappe._dict(name="WO-1", docstatus=1, open_status="Open", fabric_source_process="Knitting")
		with patch("essdee_yrp.delivery_challan_hooks.requires_exact_source_lifecycle", return_value=True):
			self.assertTrue(is_correction_supported(work_order))
		self.assertFalse(is_correction_supported(frappe._dict(work_order, open_status="Close")))

	def test_context_has_no_item_restriction(self):
		work_order = frappe._dict(name="WO-1", production_detail="IPD-1", check_permission=lambda _: None)
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=work_order),
			patch(f"{MODULE}.can_create_correction", return_value=True),
		):
			self.assertEqual(get_work_order_correction_context("WO-1"), {"can_create": True})


class TestCorrectionCloseWriteOff(TestCase):
	def make_work_order(self, open_status="Close"):
		return frappe._dict(doctype="YRP Work Order", name="WO-1", supplier="SUP", open_status=open_status)

	def test_close_writes_off_delivered_correction_stock_capped_at_balance(self):
		rows = [
			frappe._dict(
				name="ROW-1",
				item_variant="PANEL-L",
				uom="Nos",
				outstanding_qty=8,
				lot="LOT",
				received_type="Accepted",
			),
			frappe._dict(
				name="ROW-2",
				item_variant="PANEL-XL",
				uom="Nos",
				outstanding_qty=5,
				lot="LOT",
				received_type="Accepted",
			),
		]
		balances = {"PANEL-L": 20, "PANEL-XL": 3}
		with (
			patch(f"{MODULE}._delivered_correction_rows", return_value=rows),
			patch(
				"yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan._get_warehouse_for_supplier",
				return_value="SUP-WH",
			),
			patch(
				"yrp.stock.utils.get_conversion_factor",
				return_value={"conversion_factor": 1, "stock_uom": "Nos"},
			),
			patch("yrp.stock.utils.get_stock_balance", side_effect=lambda item, *a, **k: balances[item]),
			patch("yrp.stock.stock_ledger.make_sl_entries") as make_sl_entries,
		):
			write_off_correction_stock(self.make_work_order())
		entries = make_sl_entries.call_args.args[0]
		self.assertEqual(
			[(e["item"], e["warehouse"], e["qty"], e["voucher_detail_no"], e["lot"]) for e in entries],
			[("PANEL-L", "SUP-WH", -8, "ROW-1", "LOT"), ("PANEL-XL", "SUP-WH", -3, "ROW-2", "LOT")],
		)
		self.assertTrue(
			all(e["voucher_type"] == "YRP Work Order" and e["voucher_no"] == "WO-1" for e in entries)
		)

	def test_float_residual_is_not_outstanding_correction_stock(self):
		residual = frappe._dict(name="ROW-1", qty=1.33, pending_quantity=0.13)
		leftover = frappe._dict(name="ROW-2", qty=1.0, pending_quantity=0)
		close_entries = [
			frappe._dict(voucher_detail_no="ROW-1", qty=-1.2),
			frappe._dict(voucher_detail_no="ROW-2", qty=-0.9),
		]
		correction = frappe._dict(deliverables=[residual, leftover])
		with (
			patch("essdee_yrp.work_order_reopen.get_unreversed_close_entries", return_value=close_entries),
			patch(f"{MODULE}.frappe.get_all", return_value=["CORR-1"]),
			patch(f"{MODULE}.frappe.get_doc", return_value=correction),
			patch(f"{MODULE}.get_stock_qty_precision", return_value=3),
		):
			rows = _delivered_correction_rows("WO-1")
		self.assertEqual([(row.name, row.outstanding_qty) for row in rows], [("ROW-2", 0.1)])

	def test_skips_a_work_order_that_is_not_closed(self):
		with patch(f"{MODULE}._delivered_correction_rows") as rows:
			write_off_correction_stock(self.make_work_order(open_status="Close Request"))
		rows.assert_not_called()

	def test_close_owns_the_write_off_instead_of_a_generic_hook(self):
		import inspect

		from essdee_yrp import hooks
		from essdee_yrp.work_order_close import close_work_order

		self.assertNotIn("on_update_after_submit", hooks.doc_events["YRP Work Order"])
		self.assertIn("write_off_correction_stock(doc)", inspect.getsource(close_work_order))


MODULE = "essdee_yrp.work_order_correction"


class TestWorkOrderCorrection(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.work_order = _find_garment_work_order()
		if not cls.work_order:
			raise cls.skipTest(cls, "No open garment Work Order with deliverables on this site")

	def test_context_allows_creation(self):
		self.assertTrue(get_work_order_correction_context(self.work_order.name)["can_create"])

	def test_create_submits_correction_and_feeds_dc_and_grn_defaults(self):
		wo = self.work_order
		deliverable = wo.deliverables[0]
		receivable = wo.receivables[0]
		name = create_work_order_correction(
			wo.name,
			deliverable_details=_grouped(deliverable, "YRP Work Order Deliverables", 7),
			receivable_details=_grouped(receivable, "YRP Work Order Receivables", 3),
			reason="Extra panels",
		)
		correction = frappe.get_doc("YRP Work Order Correction", name)
		self.assertEqual(correction.docstatus, 1)
		self.assertEqual(correction.work_order, wo.name)
		self.assertEqual(correction.supplier, wo.supplier)
		self.assertEqual(correction.reason, "Extra panels")
		self.assertEqual(
			[(row.item_variant, row.qty, row.pending_quantity) for row in correction.deliverables],
			[(deliverable.item_variant, 7, 7)],
		)
		self.assertEqual(
			[(row.item_variant, row.qty, row.pending_quantity) for row in correction.receivables],
			[(receivable.item_variant, 3, 3)],
		)

		from essdee_yrp.work_order_actions import (
			get_delivery_challan_defaults,
			get_goods_received_note_defaults,
		)

		dc_rows = get_delivery_challan_defaults(wo.name)["correction_items"]
		self.assertIn((deliverable.item_variant, 7, name), _correction_rows(dc_rows, "qty"))
		grn_rows = get_goods_received_note_defaults(wo.name)["correction_items"]
		self.assertIn(name, {row["work_order_correction"] for row in grn_rows})
		self.assertIn(receivable.item_variant, {row["item_variant"] for row in grn_rows})

	def test_web_workspace_offers_and_runs_the_correction_command(self):
		from essdee_yrp.fabric_store.documents.work_order import (
			execute_work_order_command,
			get_work_order_workspace,
		)

		wo = self.work_order
		workspace = get_work_order_workspace(wo.name)
		self.assertIn("create_work_order_correction", workspace["capabilities"])
		self.assertTrue(execute_work_order_command(wo.name, "get_correction_context")["can_create"])
		result = execute_work_order_command(
			wo.name,
			"create_work_order_correction",
			{
				"deliverable_details": _grouped(wo.deliverables[0], "YRP Work Order Deliverables", 2),
				"receivable_details": [],
				"reason": "Web",
			},
		)
		created = result["created"]["name"]
		self.assertEqual(frappe.db.get_value("YRP Work Order Correction", created, "docstatus"), 1)
		self.assertIn(created, [row["name"] for row in result["corrections"]])

	def test_rows_without_dimensions_take_the_work_order_lot_and_default_type(self):
		wo = self.work_order
		groups = _grouped(wo.deliverables[0], "YRP Work Order Deliverables", 1)
		for group in groups:
			for item in group["items"]:
				item["dimensions"] = {}
		name = create_work_order_correction(wo.name, deliverable_details=groups)
		row = frappe.get_doc("YRP Work Order Correction", name).deliverables[0]
		self.assertEqual(row.lot, wo.lot)
		self.assertTrue(row.received_type)

	def test_web_route_workspace_lists_corrections(self):
		from essdee_yrp.fabric_store.web_workspace import get_work_order_workspace

		wo = self.work_order
		name = create_work_order_correction(
			wo.name, deliverable_details=_grouped(wo.deliverables[0], "YRP Work Order Deliverables", 1)
		)
		corrections = get_work_order_workspace(wo.name)["corrections"]
		self.assertIn(name, [row["name"] for row in corrections])

	def test_create_rejects_empty_rows(self):
		with self.assertRaises(frappe.ValidationError):
			create_work_order_correction(self.work_order.name, deliverable_details=[], receivable_details=[])

	def test_unsupported_for_cancelled_work_order(self):
		cancelled = frappe.db.get_value("YRP Work Order", {"docstatus": 2}, "name")
		if cancelled:
			self.assertFalse(is_correction_supported(frappe.get_doc("YRP Work Order", cancelled)))


def _grouped(row, child_doctype, qty):
	copy = frappe._dict(row.as_dict())
	copy.qty = qty
	copy.pending_quantity = 0
	return group_items_for_ui([copy], child_doctype)


def _correction_rows(rows, qty_field):
	return {(row["item_variant"], row[qty_field], row["work_order_correction"]) for row in rows}


def _find_garment_work_order():
	names = frappe.get_all(
		"YRP Work Order",
		filters={
			"docstatus": 1,
			"open_status": "Open",
			"is_rework": 0,
			"production_detail": ["is", "set"],
			"process_name": ["in", ["Yolk Fusing", "Ironing and Packing", "Stitching"]],
		},
		order_by="modified desc",
		pluck="name",
		limit=20,
	)
	for name in names:
		wo = frappe.get_doc("YRP Work Order", name)
		item = frappe.db.get_value("YRP Item Production Detail", wo.production_detail, "item")
		wo.deliverables = [
			row
			for row in wo.deliverables
			if frappe.db.get_value("Item", row.item_variant, "variant_of") == item
		]
		if wo.deliverables and wo.receivables and is_correction_supported(wo):
			return wo
	return None
