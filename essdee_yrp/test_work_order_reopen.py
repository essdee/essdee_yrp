from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt
from yrp.stock.utils import get_conversion_factor, get_stock_balance
from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import _get_warehouse_for_supplier
from yrp.yrp.doctype.yrp_purchase_invoice.test_yrp_purchase_invoice import (
	_work_order_for_invoice,
	_work_order_grn,
)
from yrp.yrp.doctype.yrp_work_order.yrp_work_order import _stock_dimension_values

from essdee_yrp.work_order_close import close_work_order
from essdee_yrp.work_order_reopen import reopen_work_order, restore_deliverable_stock_update


class TestWorkOrderReopen(IntegrationTestCase):
	"""Close -> Reopen round trips on throwaway Work Orders; all rolled back."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		real_get_single_value = frappe.db.get_single_value

		def get_single_value(doctype, fieldname, *args, **kwargs):
			if doctype == "YRP Settings" and fieldname == "work_order_closing_approver_role":
				return "System Manager"
			return real_get_single_value(doctype, fieldname, *args, **kwargs)

		patcher = patch.object(frappe.db, "get_single_value", side_effect=get_single_value)
		patcher.start()
		cls.addClassCleanup(patcher.stop)
		# The shared helper picks any host Lot, which may track cut bundles.
		bundle_patcher = patch("essdee_yrp.cutting.movement.validate_movement_required")
		bundle_patcher.start()
		cls.addClassCleanup(bundle_patcher.stop)

	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, "Administrator")

	def test_only_system_manager_can_reopen(self):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"reopen-{frappe.generate_hash(length=8)}@example.com",
				"first_name": "Reopen Test",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		frappe.set_user(user.name)
		with self.assertRaises(frappe.PermissionError):
			reopen_work_order("WO-DOES-NOT-EXIST")

	def test_open_work_order_cannot_be_reopened(self):
		work_order = _work_order_for_invoice(qty=1)
		with self.assertRaisesRegex(frappe.ValidationError, "Only a closed Work Order"):
			reopen_work_order(work_order.name)

	def test_close_then_reopen_restores_supplier_stock(self):
		work_order, bucket = self._closable_work_order()
		opening = self._balance(bucket)

		closed = close_work_order(work_order.name, sd_close_reason="NA")
		self.assertGreater(closed["deducted_qty"], 0)
		self.assertAlmostEqual(self._balance(bucket), opening - closed["deducted_qty"])

		result = reopen_work_order(work_order.name)

		self.assertAlmostEqual(self._balance(bucket), opening)
		self.assertAlmostEqual(result["restored_qty"], closed["deducted_qty"])
		receipt = frappe.get_doc("YRP Stock Entry", result["stock_entry"])
		self.assertEqual((receipt.purpose, receipt.docstatus), ("Material Receipt", 1))
		self.assertEqual(receipt.to_warehouse, bucket["warehouse"])
		self.assertEqual((receipt.against, receipt.against_id), ("YRP Work Order", work_order.name))
		row = receipt.items[0]
		self.assertEqual(row.item, bucket["item"])
		self.assertEqual(row.lot, bucket["dimensions"]["lot"])
		self.assertEqual(row.received_type, bucket["dimensions"]["received_type"])
		self.assertAlmostEqual(flt(row.rate), 7)

		work_order.reload()
		self.assertEqual(work_order.open_status, "Open")
		self.assertNotEqual(work_order.status, "Closed")
		self.assertFalse(work_order.closed_by)
		self.assertFalse(work_order.sd_close_reason)
		self.assertEqual(flt(work_order.deliverables[0].stock_update), 0)
		self.assertGreater(flt(work_order.total_quantity), 0)
		self.assertTrue(
			frappe.db.exists(
				"Comment",
				{
					"reference_doctype": "YRP Work Order",
					"reference_name": work_order.name,
					"content": ["like", f"%{receipt.name}%"],
				},
			)
		)

		with self.assertRaisesRegex(frappe.ValidationError, "Only a closed Work Order"):
			reopen_work_order(work_order.name)

	def test_close_after_reopen_moves_stock_but_keeps_the_first_close_valuation(self):
		work_order, bucket = self._closable_work_order()
		opening = self._balance(bucket)
		close_work_order(work_order.name, sd_close_reason="NA")
		adjustments = self._close_adjustments(work_order.name)
		first = reopen_work_order(work_order.name)

		closed = close_work_order(work_order.name, sd_close_reason="NA")
		self.assertAlmostEqual(closed["deducted_qty"], first["restored_qty"])
		self.assertAlmostEqual(self._balance(bucket), opening - closed["deducted_qty"])
		self.assertEqual(self._close_adjustments(work_order.name), adjustments)
		second = reopen_work_order(work_order.name)

		self.assertAlmostEqual(second["restored_qty"], first["restored_qty"])
		self.assertAlmostEqual(self._balance(bucket), opening)
		self.assertEqual(self._close_adjustments(work_order.name), adjustments)

	def test_reopen_restores_stock_at_zero_value_when_close_valuation_moved_it_to_outputs(self):
		work_order, bucket = self._closable_work_order()
		close_work_order(work_order.name, sd_close_reason="NA")
		with patch("essdee_yrp.work_order_reopen.has_close_valuation", return_value=True):
			result = reopen_work_order(work_order.name)

		receipt = frappe.get_doc("YRP Stock Entry", result["stock_entry"])
		self.assertEqual(flt(receipt.items[0].rate), 0)
		self.assertEqual(receipt.items[0].allow_zero_valuation_rate, 1)
		values = frappe.get_all(
			"YRP Stock Ledger Entry",
			filters={"voucher_type": "YRP Stock Entry", "voucher_no": receipt.name, "is_cancelled": 0},
			pluck="stock_value_difference",
		)
		self.assertTrue(values)
		self.assertAlmostEqual(sum(flt(value) for value in values), 0)
		self.assertAlmostEqual(self._balance(bucket), result["restored_qty"])

	def test_reopen_fails_loudly_when_close_ledger_is_missing(self):
		work_order, _bucket = self._closable_work_order()
		close_work_order(work_order.name, sd_close_reason="NA")
		frappe.db.set_value(
			"YRP Stock Ledger Entry",
			{"voucher_type": "YRP Work Order", "voucher_no": work_order.name},
			"is_cancelled",
			1,
		)
		with self.assertRaisesRegex(frappe.ValidationError, "close stock ledger"):
			reopen_work_order(work_order.name)
		self.assertEqual(frappe.db.get_value("YRP Work Order", work_order.name, "open_status"), "Close")

	def test_restore_rounds_away_float_residual_stock_update(self):
		row = frappe._dict(name="ROW-1", item_variant="ITEM", uom="Nos", stock_update=1.33)
		entries = [frappe._dict(voucher_detail_no="ROW-1", qty=qty) for qty in (-0.13, -1.2)]
		doc = frappe._dict(deliverables=[row])
		with patch(
			"essdee_yrp.work_order_reopen.get_conversion_factor", return_value={"conversion_factor": 1}
		):
			restore_deliverable_stock_update(doc, entries)
		self.assertEqual(row.stock_update, 0)

	def test_float_residual_stock_update_does_not_block_reopen(self):
		doc = frappe._dict(
			name="WO-1",
			docstatus=1,
			open_status="Close",
			deliverables=[frappe._dict(name="ROW-1", stock_update=5.551115123125783e-17)],
		)
		with (
			patch.object(frappe.db, "sql"),
			patch.object(frappe, "get_doc", return_value=doc),
			patch("essdee_yrp.work_order_reopen.get_unreversed_close_entries", return_value=[]),
			patch("essdee_yrp.work_order_reopen.get_stock_qty_precision", return_value=3),
			patch(
				"essdee_yrp.work_order_reopen.restore_deliverable_stock_update",
				side_effect=AssertionError("reached"),
			),
		):
			with self.assertRaisesRegex(AssertionError, "reached"):
				reopen_work_order("WO-1")

	def _closable_work_order(self):
		"""Submitted WO with 3 of 5 pieces delivered and that leftover held at the supplier."""
		work_order = _work_order_for_invoice(qty=5)
		row = work_order.deliverables[0]
		self._keep_one_supplier_warehouse(work_order.supplier)
		warehouse = _get_warehouse_for_supplier(work_order.supplier)
		dimensions = _stock_dimension_values(work_order, row)
		stock_uom = get_conversion_factor(row.item_variant, row.uom).get("stock_uom") or row.uom
		receipt = frappe.new_doc("YRP Stock Entry")
		receipt.update({"purpose": "Material Receipt", "to_warehouse": warehouse})
		receipt.append(
			"items", {"item": row.item_variant, "qty": 3, "uom": stock_uom, "rate": 7, **dimensions}
		)
		receipt.insert(ignore_permissions=True)
		receipt.submit()
		frappe.db.set_value("YRP Work Order Deliverables", row.name, "pending_quantity", 2)
		_work_order_grn(work_order, qty=5)
		work_order.reload()
		return work_order, {"item": row.item_variant, "warehouse": warehouse, "dimensions": dimensions}

	def _keep_one_supplier_warehouse(self, supplier):
		"""The supplier insert hook adds a second warehouse; close needs exactly one."""
		warehouses = frappe.get_all("Warehouse", filters={"supplier": supplier, "disabled": 0}, pluck="name")
		for warehouse in warehouses[1:]:
			frappe.db.set_value("Warehouse", warehouse, "disabled", 1)

	def _balance(self, bucket):
		return flt(get_stock_balance(bucket["item"], bucket["warehouse"], **bucket["dimensions"]))

	def _close_adjustments(self, work_order):
		return frappe.get_all(
			"YRP Stock Valuation Adjustment",
			filters={"source_doctype": "YRP Work Order", "source_name": work_order, "docstatus": 1},
			pluck="name",
		)
