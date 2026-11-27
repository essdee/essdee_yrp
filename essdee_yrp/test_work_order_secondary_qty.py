import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.fabric_store.documents.work_order import (
	execute_work_order_command,
	get_work_order_workspace,
)


class TestWorkOrderSecondaryQtyCommands(IntegrationTestCase):
	def submitted_cloth_work_order(self):
		name = frappe.db.sql(
			"""select wo.name from `tabYRP Work Order` wo
			join `tabYRP Process` process on process.name = wo.process_name
			where wo.docstatus = 1 and process.is_cloth_process = 1
				and exists (select 1 from `tabYRP Work Order Receivables` r
					where r.parent = wo.name and ifnull(r.secondary_uom, '') != '')
			order by wo.modified desc limit 1"""
		)
		if not name:
			self.skipTest("Needs a submitted cloth Work Order with a Secondary UOM")
		return frappe.get_doc("YRP Work Order", name[0][0])

	def test_submitted_work_order_offers_secondary_qty_edit(self):
		doc = self.submitted_cloth_work_order()
		workspace = get_work_order_workspace(doc.name)
		self.assertIn("edit_secondary_qty", workspace["capabilities"])

	def test_secondary_qty_command_edits_submitted_rows_and_print(self):
		doc = self.submitted_cloth_work_order()
		row = next(row for row in doc.receivables if row.secondary_uom)
		rows = execute_work_order_command(doc.name, "get_secondary_quantities")["rows"]
		self.assertIn(row.name, {item["name"] for item in rows})

		execute_work_order_command(doc.name, "update_secondary_quantities", {"quantities": {row.name: 45}})

		saved = frappe.db.get_value(
			"YRP Work Order Receivables", row.name, ["secondary_qty", "qty"], as_dict=True
		)
		self.assertEqual((saved.secondary_qty, saved.qty), (45, row.qty))
		self.assertEqual(frappe.db.get_value("YRP Work Order", doc.name, "docstatus"), 1)
		html = frappe.get_print("YRP Work Order", doc.name, "Essdee Work Order Receivables", no_letterhead=1)
		self.assertIn(f"45 {row.secondary_uom}", html)
