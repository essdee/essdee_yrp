import json

import frappe
from frappe.tests import IntegrationTestCase
from yrp import attribute_links as attribute_db
from yrp.attribute_links import value as _attribute_value

from essdee_yrp.cutting.movement import _cancel_exact_bundle_entries
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_bundle_movement_ledger.sd_yrp_cut_bundle_movement_ledger import (
	get_previous_entry,
	make_cut_bundle_ledger,
)

LEDGER = "SD YRP Cut Bundle Movement Ledger"
POSTING_DATE = "2099-01-01"
QUANTITY = 7


class TestCutBundleCancelSameVoucher(IntegrationTestCase):
	"""A voucher's own rows never count as a later movement when it is cancelled."""

	def setUp(self):
		frappe.db.savepoint("cut_bundle_cancel_same_voucher")
		self.addCleanup(frappe.db.rollback, save_point="cut_bundle_cancel_same_voucher")
		row = frappe.db.sql(
			"""
			SELECT lot, item, size, colour, panel, supplier FROM `tabSD YRP Cut Bundle Movement Ledger`
			WHERE collapsed_bundle = 0 AND is_cancelled = 0 AND IFNULL(panel, '') != ''
			LIMIT 1
			""",
			as_dict=True,
		)
		challans = frappe.get_all("YRP Delivery Challan", filters={"docstatus": 1}, pluck="name", limit=2)
		opening = frappe.get_all("YRP Goods Received Note", filters={"docstatus": 1}, pluck="name", limit=1)
		if not row or len(challans) < 2 or not opening:
			self.skipTest("No exact-bundle ledger oracle is available")
		row = attribute_db.business_values(row)[0]
		self.bundle = {
			"lot": row.lot,
			"item": row.item,
			"size": _attribute_value(row.size),
			"colour": _attribute_value(row.colour),
			"panel": _attribute_value(row.panel),
			"supplier": row.supplier,
			"lay_no": 990001,
			"bundle_no": frappe.generate_hash(length=8),
			"shade": "TEST",
			"set_combination": json.dumps({"major_colour": "Same Voucher Test"}),
			"posting_date": POSTING_DATE,
		}
		self.challans = challans
		self.move("YRP Goods Received Note", opening[0], "10:00:00", [QUANTITY])

	def move(self, voucher_type, voucher_no, posting_time, quantities):
		"""Mirror apply_transaction: one ledger call per location side, in order."""
		for quantity in quantities:
			entry = dict(
				self.bundle,
				voucher_type=voucher_type,
				voucher_no=voucher_no,
				posting_time=posting_time,
				quantity=quantity,
				is_cancelled=0,
			)
			make_cut_bundle_ledger([entry])
		return frappe._dict(doctype=voucher_type, name=voucher_no)

	def balance(self):
		entry = dict(self.bundle, posting_date="9999-12-31", posting_time="23:59:59")
		return get_previous_entry(entry)[0]

	def active_rows(self, voucher):
		return frappe.get_all(
			LEDGER,
			filters={"voucher_type": voucher.doctype, "voucher_no": voucher.name, "is_cancelled": 0},
			pluck="quantity",
		)

	def test_same_location_challan_cancels_its_own_rows(self):
		before = self.balance()
		challan = self.move("YRP Delivery Challan", self.challans[0], "11:00:00", [-QUANTITY, QUANTITY])
		self.assertEqual(sorted(self.active_rows(challan)), [-QUANTITY, QUANTITY])

		_cancel_exact_bundle_entries(challan)

		self.assertEqual(self.active_rows(challan), [])
		after = self.balance()
		self.assertEqual(after.name, before.name)
		self.assertEqual(after.quantity_after_transaction, QUANTITY)

	def test_later_movement_from_another_voucher_still_blocks_cancel(self):
		challan = self.move("YRP Delivery Challan", self.challans[0], "11:00:00", [-QUANTITY, QUANTITY])
		later = self.move("YRP Delivery Challan", self.challans[1], "12:00:00", [-QUANTITY])

		with self.assertRaisesRegex(frappe.ValidationError, "Cancel the later cut-bundle movement"):
			_cancel_exact_bundle_entries(challan)
		self.assertEqual(sorted(self.active_rows(challan)), [-QUANTITY, QUANTITY])

		_cancel_exact_bundle_entries(later)
		_cancel_exact_bundle_entries(challan)
		self.assertEqual(self.balance().quantity_after_transaction, QUANTITY)
