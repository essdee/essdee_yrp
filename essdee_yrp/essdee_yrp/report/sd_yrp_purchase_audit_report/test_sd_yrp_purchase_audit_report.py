import json

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.report.sd_yrp_purchase_audit_report.sd_yrp_purchase_audit_report import (
	execute,
	item_query,
)

DATE = "2099-03-10"
NEXT_DATE = "2099-03-20"


class TestPurchaseAuditReport(IntegrationTestCase):
	def setUp(self):
		self.key = frappe.generate_hash(length=8)
		self.supplier = self.make_supplier("Audit Maker")
		self.warehouse = self.make_warehouse("Audit Store", self.supplier)
		self.template = self.make_item("T", template=True)
		self.variant = self.make_item("V", parent=self.template)

	def make_supplier(self, name):
		return frappe.get_doc({"doctype": "Supplier", "supplier_name": f"{name} {self.key}"}).insert().name

	def make_warehouse(self, name, supplier=None):
		company = frappe.get_all("Company", pluck="name", limit=1)[0]
		doc = {"doctype": "Warehouse", "warehouse_name": f"{name} {self.key}", "company": company}
		return frappe.get_doc({**doc, "supplier": supplier}).insert(ignore_permissions=True).name

	def make_item(self, code, parent=None, template=False):
		name = f"AUD-{self.key}-{code}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"name": name,
				"item_code": name,
				"item_name": name,
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": "Nos",
				"has_variants": int(template),
				"variant_of": parent,
			}
		).db_insert()
		return name

	def make_voucher(self, doctype, **fields):
		doc = frappe.get_doc({"doctype": doctype, "name": f"AUD-{frappe.generate_hash(length=10)}"})
		doc.update({"docstatus": 1, "posting_date": DATE, **fields})
		doc.db_insert()
		return doc

	def add_entry(self, voucher, qty, date=DATE, warehouse=None, item=None, lot=None, **fields):
		frappe.get_doc(
			{
				"doctype": "YRP Stock Ledger Entry",
				"item": item or self.variant,
				"warehouse": warehouse or self.warehouse,
				"posting_date": date,
				"posting_time": "10:00:00",
				"posting_datetime": f"{date} 10:00:00",
				"qty": qty,
				"voucher_type": voucher.doctype,
				"voucher_no": voucher.name,
				"lot": lot,
				"received_type": None,
				"is_cancelled": 0,
				"docstatus": 1,
				**fields,
			}
		).db_insert()

	def run_report(self, **filters):
		base = {"from_date": DATE, "to_date": NEXT_DATE, "warehouse": self.warehouse}
		return execute({**base, **filters})[1]

	def make_all_movements(self):
		grn = self.make_voucher(
			"YRP Goods Received Note", against="Purchase Order", supplier=self.supplier, is_return=0
		)
		wo_grn = self.make_voucher(
			"YRP Goods Received Note", against="YRP Work Order", supplier=self.supplier, is_return=0
		)
		wo_return = self.make_voucher("YRP Goods Received Note", against="YRP Work Order", is_return=1)
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		issue = self.make_voucher("YRP Stock Entry", purpose="Material Issue")
		consumed = self.make_voucher("YRP Stock Entry", purpose="Material Consumed")
		dispatch = self.make_voucher("YRP Stock Entry", purpose="Stock Dispatch")
		send = self.make_voucher("YRP Stock Entry", purpose="Send to Warehouse")
		receive = self.make_voucher("YRP Stock Entry", purpose="Receive at Warehouse")
		add = self.make_voucher("YRP Stock Update", update_type="Add")
		reduce = self.make_voucher("YRP Stock Update", update_type="Reduce")
		dc = self.make_voucher("YRP Delivery Challan", supplier=self.supplier)
		conversion = self.make_voucher("SD YRP Item Conversion")
		movements = [
			(grn, 100),
			(wo_grn, 11),
			(wo_grn, -12),
			(wo_return, 7),
			(wo_return, -1),
			(receipt, 20),
			(issue, -5),
			(consumed, -4),
			(dispatch, -3),
			(send, -8),
			(receive, 9),
			(add, 3),
			(reduce, -2),
			(dc, 13),
			(dc, -30),
			(conversion, 4),
			(conversion, -6),
		]
		for voucher, qty in movements:
			self.add_entry(voucher, qty)

	def test_each_voucher_lands_in_its_named_column(self):
		self.make_all_movements()
		columns, rows = execute({"from_date": DATE, "to_date": NEXT_DATE, "warehouse": self.warehouse})
		(row,) = rows
		expected = {
			"po_grn": 100,
			"wo_grn": 11,
			"wo_grn_consumed": 12,
			"wo_return_grn": 7,
			"wo_return_grn_out": 1,
			"se_material_receipt": 20,
			"se_material_issue": 5,
			"material_consumed": 4,
			"stock_dispatch": 3,
			"sent_warehouse": 8,
			"received_warehouse": 9,
			"added_stock": 3,
			"reduced_stock": 2,
			"dc_received": 13,
			"dc_qty": 30,
			"conversion_inward": 4,
			"conversion_outward": 6,
		}
		self.assertEqual({field: row[field] for field in expected}, expected)
		labels = {column["fieldname"]: column["label"] for column in columns}
		self.assertEqual(labels["wo_return_grn"], "WO Return GRN")
		self.assertEqual(labels["material_consumed"], "Material Consumed")
		self.assertFalse([label for label in labels.values() if "Other" in label])
		self.assertEqual(row["suppliers"], self.supplier)

	def test_unmapped_voucher_gets_a_column_named_after_its_source(self):
		voucher = self.make_voucher("SD YRP FG Stock Entry")
		self.add_entry(voucher, 6)
		columns, (row,) = execute({"from_date": DATE, "to_date": NEXT_DATE, "warehouse": self.warehouse})
		column = next(column for column in columns if column["label"] == "SD YRP FG Stock Entry In")
		self.assertEqual(row[column["fieldname"]], 6)
		self.assertEqual(row["total_inward"], 6)

	def test_lot_transfer_inside_warehouse_nets_out(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		transfer = self.make_voucher("SD YRP Lot Transfer")
		self.add_entry(receipt, 12, date="2099-03-01", lot=f"FROM-{self.key}")
		self.add_entry(transfer, 12, lot=f"TO-{self.key}")
		self.add_entry(transfer, -12, lot=f"FROM-{self.key}")
		columns, (row,) = execute({"from_date": DATE, "to_date": NEXT_DATE, "warehouse": self.warehouse})
		self.assertEqual((row["opening_stock"], row["total_inward"], row["total_outward"]), (12, 0, 0))
		self.assertEqual(row["stock_balance"], 12)
		fields = [column["fieldname"] for column in columns]
		self.assertNotIn("lot", fields)
		self.assertNotIn("lot", row)

	def test_lot_transfer_across_warehouses_keeps_its_net(self):
		transfer = self.make_voucher("SD YRP Lot Transfer")
		self.add_entry(transfer, 12, lot=f"TO-{self.key}")
		other = self.make_warehouse("Other Store")
		self.add_entry(transfer, -12, lot=f"FROM-{self.key}", warehouse=other)
		(row,) = self.run_report()
		self.assertEqual((row["lot_transfer_in"], row["total_inward"], row["stock_balance"]), (12, 12, 12))

	def test_rows_split_by_variant_and_received_type_not_lot(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		issue = self.make_voucher("YRP Stock Entry", purpose="Material Issue")
		self.add_entry(receipt, 10, lot=f"LOT-{self.key}", received_type="Accepted")
		self.add_entry(receipt, 6, date=NEXT_DATE, lot=f"OTHER-{self.key}", received_type="Accepted")
		self.add_entry(issue, -4, lot=f"LOT-{self.key}", received_type="Accepted")
		self.add_entry(receipt, 3, lot=f"LOT-{self.key}", received_type="Rejected")
		rows = {row["received_type"]: row for row in self.run_report()}
		self.assertEqual(set(rows), {"Accepted", "Rejected"})
		accepted = rows["Accepted"]
		self.assertEqual((accepted["se_material_receipt"], accepted["se_material_issue"]), (16, 4))
		self.assertEqual(rows["Rejected"]["total_inward"], 3)
		only_rejected = self.run_report(received_type="Rejected")
		self.assertEqual([row["received_type"] for row in only_rejected], ["Rejected"])

	def test_lot_and_supplier_filters_are_gone(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		self.add_entry(receipt, 5, lot=f"LOT-{self.key}")
		self.assertEqual(len(self.run_report(lot="missing", supplier="missing")), 1)

	def test_columns_read_opening_then_movements_then_balance(self):
		self.make_all_movements()
		columns, _rows = execute({"from_date": DATE, "to_date": NEXT_DATE, "warehouse": self.warehouse})
		fields = [column["fieldname"] for column in columns]
		self.assertEqual(fields[:5], ["item", "item_variant", "item_group", "warehouse", "received_type"])
		opening, total_in = fields.index("opening_stock"), fields.index("total_inward")
		total_out, balance = fields.index("total_outward"), fields.index("stock_balance")
		self.assertEqual(opening, 5)
		self.assertLess(fields.index("po_grn"), total_in)
		self.assertLess(total_in, fields.index("dc_qty"))
		self.assertLess(fields.index("dc_qty"), total_out)
		self.assertEqual(balance, total_out + 1)
		for field in ("difference", "reconciliation_adjustment", "reconciliation_in", "lot_transfer_in"):
			self.assertNotIn(field, fields)
		for column in columns:
			self.assertFalse(column.get("disable_total"))

	def test_rejects_missing_dates_or_warehouse_and_reversed_dates(self):
		missing_warehouse = {"from_date": DATE, "to_date": NEXT_DATE}
		reversed_dates = {"from_date": NEXT_DATE, "to_date": DATE, "warehouse": self.warehouse}
		for filters in ({"from_date": DATE, "warehouse": self.warehouse}, missing_warehouse, reversed_dates):
			with self.subTest(filters=filters), self.assertRaises(frappe.ValidationError):
				execute(filters)

	def test_summarized_view_drops_bucket_columns(self):
		self.make_all_movements()
		columns, _rows = execute(
			{"from_date": DATE, "to_date": NEXT_DATE, "warehouse": self.warehouse, "summarized_view": 1}
		)
		fields = [column["fieldname"] for column in columns]
		self.assertEqual(
			fields[-5:], ["opening_stock", "total_inward", "total_outward", "stock_balance", "suppliers"]
		)
		self.assertNotIn("po_grn", fields)

	def test_month_wise_report_splits_totals_per_month(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		issue = self.make_voucher("YRP Stock Entry", purpose="Material Issue")
		reconciliation = self.make_voucher("YRP Stock Reconciliation")
		self.add_entry(receipt, 10)
		self.add_entry(issue, -4, date="2099-04-02")
		self.add_entry(reconciliation, 0, date="2099-04-05", qty_after_transaction=9)
		self.add_entry(receipt, 6, date="2099-05-31")
		filters = {"to_date": "2099-05-31", "summarized_view": 1, "month_wise_report": 1}
		columns, rows = execute({"from_date": DATE, "warehouse": self.warehouse, **filters})
		labels = [column["label"] for column in columns if column["fieldtype"] == "Float"]
		self.assertEqual(
			labels,
			[
				"Opening Stock",
				"Mar 2099 Inward",
				"Mar 2099 Outward",
				"Apr 2099 Inward",
				"Apr 2099 Outward",
				"May 2099 Inward",
				"May 2099 Outward",
				"Total Inward",
				"Total Outward",
				"Stock Balance",
			],
		)
		(row,) = rows
		months = [row[column["fieldname"]] for column in columns if column["fieldtype"] == "Float"][1:7]
		self.assertEqual(months, [10, 0, 3, 4, 6, 0])
		self.assertEqual(sum(months[0::2]), row["total_inward"])
		self.assertEqual(sum(months[1::2]), row["total_outward"])
		self.assertEqual(row["stock_balance"], 15)

	def test_month_wise_report_needs_summarized_view(self):
		self.make_all_movements()
		columns, _rows = execute(
			{"from_date": DATE, "to_date": NEXT_DATE, "warehouse": self.warehouse, "month_wise_report": 1}
		)
		self.assertIn("po_grn", [column["fieldname"] for column in columns])

	def test_suppliers_column_lists_inward_suppliers(self):
		self.make_all_movements()
		other = self.make_supplier("Other Maker")
		other_dc = self.make_voucher("YRP Delivery Challan", supplier=other, from_location=other)
		self.add_entry(other_dc, -11)
		(row,) = self.run_report()
		self.assertEqual(row["suppliers"], self.supplier)

	def test_zero_bucket_columns_are_hidden(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		self.add_entry(receipt, 5)
		columns, _rows = execute({"from_date": DATE, "to_date": NEXT_DATE, "warehouse": self.warehouse})
		fields = [column["fieldname"] for column in columns]
		self.assertIn("se_material_receipt", fields)
		self.assertNotIn("po_grn", fields)
		self.assertIn("total_outward", fields)

	def test_item_filters_match_template_and_variant(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		standalone = self.make_item("S")
		self.add_entry(receipt, 2)
		self.add_entry(receipt, 5, item=standalone)
		cases = [
			({"item": self.template}, {self.variant}),
			({"item": standalone}, {standalone}),
			({"item_variant": self.variant}, {self.variant}),
			({"item": standalone, "item_variant": self.variant}, set()),
			({"item": [self.template, standalone]}, {self.variant, standalone}),
			({"item": json.dumps([standalone])}, {standalone}),
			({"item": []}, {self.variant, standalone}),
		]
		for filters, expected in cases:
			with self.subTest(filters=filters):
				self.assertEqual({row["item_variant"] for row in self.run_report(**filters)}, expected)

	def test_item_group_filter_includes_child_groups(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		self.add_entry(receipt, 2)
		group = frappe.db.get_value("Item", self.variant, "item_group")
		root = frappe.db.get_value("Item Group", group, "parent_item_group")
		other = frappe.db.get_value("Item Group", {"name": ["!=", group], "is_group": 0}, "name")
		self.assertEqual(len(self.run_report(item_group=root)), 1)
		self.assertEqual(len(self.run_report(item_group=group)), 1)
		self.assertEqual(self.run_report(item_group=other), [])
		self.assertEqual(len(self.run_report(item_group=[other, group])), 1)

	def test_item_query_limits_options_to_item_group_tree(self):
		standalone = self.make_item("S")
		parent = self.make_item_group("Parent", is_group=1)
		child = self.make_item_group("Child", parent=parent)
		frappe.db.set_value("Item", self.variant, "item_group", child)
		cases = [
			({}, {self.template, standalone}),
			({"variant": 1}, {self.variant, standalone}),
			({"item_group": [parent]}, {self.template}),
			({"item_group": json.dumps([child]), "variant": 1}, {self.variant}),
			({"item_group": [parent, child], "variant": 1}, {self.variant}),
		]
		for filters, expected in cases:
			with self.subTest(filters=filters):
				rows = item_query("Item", f"AUD-{self.key}", "name", 0, 20, filters)
				self.assertEqual({row[0] for row in rows}, expected)

	def make_item_group(self, name, parent="All Item Groups", is_group=0):
		doc = {"doctype": "Item Group", "item_group_name": f"AUD {name} {self.key}"}
		doc.update(parent_item_group=parent, is_group=is_group)
		return frappe.get_doc(doc).insert(ignore_permissions=True).name

	def test_stock_balance_is_closing_qty_at_to_date(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		issue = self.make_voucher("YRP Stock Entry", purpose="Material Issue")
		reconciliation = self.make_voucher("YRP Stock Reconciliation")
		moved, reconciled = f"LOT-{self.key}", f"RECON-{self.key}"
		self.add_entry(receipt, 50, date="2099-03-01", lot=moved)
		self.add_entry(receipt, 10, lot=moved)
		self.add_entry(issue, -4, lot=moved)
		self.add_entry(receipt, 100, date="2099-04-01", lot=moved)
		self.add_entry(receipt, 7, date="2099-03-01", lot=reconciled)
		self.add_entry(reconciliation, 0, date="2099-03-05", lot=reconciled, qty_after_transaction=20)
		self.add_entry(receipt, 5, lot=reconciled)
		views = ({}, {"summarized_view": 1}, {"summarized_view": 1, "month_wise_report": 1})
		for view in views:
			with self.subTest(view=view):
				columns, rows = execute(
					{"from_date": DATE, "to_date": NEXT_DATE, "warehouse": self.warehouse, **view}
				)
				self.assertEqual(columns[-2]["fieldname"], "stock_balance")
				self.assertEqual([(row["opening_stock"], row["stock_balance"]) for row in rows], [(70, 81)])

	def test_stock_without_movement_still_shows_a_row(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		self.add_entry(receipt, 8, date="2099-03-01")
		(row,) = self.run_report()
		self.assertEqual((row["opening_stock"], row["total_inward"], row["stock_balance"]), (8, 0, 8))
		self.assertEqual((row["item"], row["item_variant"]), (self.template, self.variant))

	def test_reconciliation_inside_range_counts_as_movement(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		reconciliation = self.make_voucher("YRP Stock Reconciliation")
		lot = f"RECON-{self.key}"
		self.add_entry(receipt, 7, date="2099-03-01", lot=lot)
		self.add_entry(reconciliation, 0, date="2099-03-05", lot=lot, qty_after_transaction=30)
		self.add_entry(receipt, 5, lot=lot)
		self.add_entry(reconciliation, -15, date="2099-03-15", lot=lot, qty_after_transaction=20)
		self.add_entry(receipt, 3, date="2099-03-18", lot=lot)
		self.add_entry(reconciliation, 0, date="2099-03-19", lot=lot, qty_after_transaction=40)
		(row,) = self.run_report()
		fields = ("opening_stock", "reconciliation_in", "reconciliation_out", "total_inward", "total_outward")
		self.assertEqual(tuple(row[field] for field in fields), (30, 17, 15, 25, 15))
		self.assertEqual(row["stock_balance"], 40)

	def test_reconciliation_is_measured_per_lot(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		reconciliation = self.make_voucher("YRP Stock Reconciliation")
		self.add_entry(receipt, 10, date="2099-03-01", lot=f"A-{self.key}")
		self.add_entry(receipt, 5, date="2099-03-01", lot=f"B-{self.key}")
		self.add_entry(reconciliation, 0, lot=f"A-{self.key}", qty_after_transaction=4)
		(row,) = self.run_report()
		self.assertEqual((row["opening_stock"], row["reconciliation_out"], row["stock_balance"]), (15, 6, 9))

	def test_rows_reconcile_to_stock_balance_in_every_view(self):
		self.make_all_movements()
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		transfer = self.make_voucher("SD YRP Lot Transfer")
		reconciliation = self.make_voucher("YRP Stock Reconciliation")
		lot = f"LOT-{self.key}"
		self.add_entry(receipt, 40, date="2099-03-01", lot=lot)
		self.add_entry(transfer, -15, lot=lot)
		self.add_entry(reconciliation, 0, date="2099-03-12", lot=lot, qty_after_transaction=18)
		self.add_entry(transfer, 15, date="2099-03-15")
		views = ({}, {"summarized_view": 1}, {"summarized_view": 1, "month_wise_report": 1})
		for view in views:
			with self.subTest(view=view):
				rows = self.run_report(**view)
				self.assertTrue(rows)
				for row in rows:
					net = row["total_inward"] - row["total_outward"]
					self.assertEqual(row["opening_stock"] + net, row["stock_balance"])
