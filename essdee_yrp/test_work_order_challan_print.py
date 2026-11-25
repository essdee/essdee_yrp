import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from essdee_yrp.print_helpers import (
	WORK_ORDER_CHALLAN_TABLES,
	get_work_order_challan_items,
	get_work_order_correction_challan_items,
	prepare_print_document,
)

FORMATS = {
	"deliverables": "Essdee Work Order Deliverables",
	"receivables": "Essdee Work Order Receivables",
}


def printed_total(groups):
	return sum(
		flt(detail.get("delivered_quantity"))
		for group in groups
		for item in group.get("items") or []
		for detail in (item.get("values") or {}).values()
	)


class TestWorkOrderChallanPrint(IntegrationTestCase):
	def work_order(self):
		name = frappe.db.sql(
			"""select wo.name from `tabYRP Work Order` wo
			where wo.docstatus = 1
				and exists (select 1 from `tabYRP Work Order Deliverables` d where d.parent = wo.name)
				and exists (select 1 from `tabYRP Work Order Receivables` r where r.parent = wo.name)
			order by wo.modified desc limit 1"""
		)
		if not name:
			self.skipTest("Needs a submitted Work Order with deliverables and receivables")
		doc = frappe.get_doc("YRP Work Order", name[0][0])
		prepare_print_document(doc)
		return doc

	def test_items_keep_every_row_quantity(self):
		doc = self.work_order()
		for table in FORMATS:
			with self.subTest(table=table):
				expected = sum(flt(row.qty) for row in doc.get(table))
				self.assertAlmostEqual(printed_total(get_work_order_challan_items(doc, table)), expected, 3)

	def test_unknown_table_fails(self):
		with self.assertRaises(frappe.ValidationError):
			get_work_order_challan_items(frappe._dict(), "work_order_calculated_items")

	def test_formats_print_the_dc_header(self):
		doc = self.work_order()
		for table, print_format in FORMATS.items():
			with self.subTest(print_format=print_format):
				html = frappe.get_print("YRP Work Order", doc.name, print_format, no_letterhead=1)
				self.assertIn("Particulars", html)
				self.assertIn(doc.supplier_name or doc.supplier, html)
				self.assertIn(doc.delivery_location_name or doc.delivery_location, html)
				self.assertIn("Receivables" if table == "receivables" else "Deliverables", html)

	def corrected_work_order(self):
		name = frappe.db.get_value("YRP Work Order Correction", {"docstatus": 1}, "work_order")
		if not name:
			self.skipTest("Needs a submitted YRP Work Order Correction")
		doc = frappe.get_doc("YRP Work Order", name)
		prepare_print_document(doc)
		return doc

	def submitted_correction_rows(self, work_order, table):
		return frappe.db.sql(
			f"""select c.name, sum(r.qty) from `tabYRP Work Order Correction` c
			join `tab{WORK_ORDER_CHALLAN_TABLES[table]}` r on r.parent = c.name
				and r.parenttype = 'YRP Work Order Correction' and r.parentfield = %s
			where c.work_order = %s and c.docstatus = 1
			group by c.name order by c.correction_date, c.creation""",
			(table, work_order),
		)

	def test_corrections_list_every_submitted_correction_row(self):
		doc = self.corrected_work_order()
		for table in FORMATS:
			with self.subTest(table=table):
				expected = self.submitted_correction_rows(doc.name, table)
				printed = get_work_order_correction_challan_items(doc, table)
				self.assertEqual([row["name"] for row in printed], [row[0] for row in expected])
				for correction, (_, quantity) in zip(printed, expected, strict=True):
					self.assertAlmostEqual(printed_total(correction["groups"]), flt(quantity), 3)

	def test_cancelled_corrections_are_not_printed(self):
		cancelled = frappe.db.get_value("YRP Work Order Correction", {"docstatus": 2}, ["name", "work_order"])
		if not cancelled:
			self.skipTest("Needs a cancelled YRP Work Order Correction")
		doc = frappe.get_doc("YRP Work Order", cancelled[1])
		for table in FORMATS:
			printed = [row["name"] for row in get_work_order_correction_challan_items(doc, table)]
			self.assertNotIn(cancelled[0], printed)

	def test_formats_print_the_corrections_section(self):
		doc = self.corrected_work_order()
		for table, print_format in FORMATS.items():
			with self.subTest(print_format=print_format):
				html = frappe.get_print("YRP Work Order", doc.name, print_format, no_letterhead=1)
				for name, _ in self.submitted_correction_rows(doc.name, table):
					self.assertIn("Work Order Corrections", html)
					self.assertIn(name, html)
