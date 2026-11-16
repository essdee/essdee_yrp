import frappe
from frappe.tests.utils import FrappeTestCase
from yrp.yrp.doctype.yrp_goods_received_note.test_purchase_order_grn import (
	_default_received_type,
	_purchase_order,
	_purchase_order_grn,
	_warehouse,
)


class TestGRNStockRowsLocked(FrappeTestCase):
	"""A submitted GRN's stock rows must keep matching its ledger and PO."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_default_received_type()

	def submitted_grn(self):
		warehouse = _warehouse(f"_T_Lock_{frappe.generate_hash(length=6)}")
		purchase_order = _purchase_order(qty=5, warehouse=warehouse)
		grn = _purchase_order_grn(purchase_order, qty=2)
		grn.submit()
		grn.reload()
		return grn

	def test_removing_row_after_submit_is_blocked(self):
		grn = self.submitted_grn()
		grn.set("items", grn.items[1:])
		with self.assertRaises(frappe.UpdateAfterSubmitError):
			grn.save(ignore_permissions=True)

	def test_adding_row_after_submit_is_blocked(self):
		grn = self.submitted_grn()
		grn.append("items", frappe.copy_doc(grn.items[0]))
		with self.assertRaises(frappe.UpdateAfterSubmitError):
			grn.save(ignore_permissions=True)

	def test_allow_on_submit_header_still_saves(self):
		grn = self.submitted_grn()
		grn.transfer_complete = 1
		grn.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value(grn.doctype, grn.name, "transfer_complete"), 1)
