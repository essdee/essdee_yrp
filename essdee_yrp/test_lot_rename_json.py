import frappe
from frappe.tests import IntegrationTestCase


def _insert_child(doctype, **values):
	row = frappe.get_doc(
		{"doctype": doctype, "parent": "lot-rename-test", "parenttype": "x", "parentfield": "x", **values}
	)
	row.db_insert()
	return row.name


def _json(doctype, name, fieldname):
	return frappe.parse_json(frappe.db.get_value(doctype, name, fieldname))


class TestStockDimensionRename(IntegrationTestCase):
	def make_lot(self):
		return (
			frappe.get_doc({"doctype": "SD YRP Lot", "lot_name": "ZZ-REN-" + frappe.generate_hash(length=8)})
			.insert()
			.name
		)

	def grn_deliverable(self, dimensions):
		return _insert_child(
			"SD YRP GRN Deliverable",
			item_variant="x",
			quantity=1,
			uom="Nos",
			stock_dimensions=frappe.as_json(dimensions),
		)

	def test_lot_rename_rewrites_grn_deliverable_stock_dimensions(self):
		old = self.make_lot()
		row = self.grn_deliverable({"lot": old, "received_type": "Accepted"})
		decoy = self.grn_deliverable({"lot": old + "X", "received_type": "Accepted"})
		new = old + "-NEW"

		frappe.rename_doc("SD YRP Lot", old, new)

		self.assertEqual(
			_json("SD YRP GRN Deliverable", row, "stock_dimensions"),
			{"lot": new, "received_type": "Accepted"},
		)
		self.assertEqual(_json("SD YRP GRN Deliverable", decoy, "stock_dimensions")["lot"], old + "X")

	def test_lot_rename_rewrites_nested_ui_payload(self):
		old = self.make_lot()
		payload = {
			"items": [
				{"name": "x", "dimensions": {"lot": old, "received_type": "Accepted"}, "values": {old: 1}}
			]
		}
		row = _insert_child("SD YRP Lot Transfer Item", stock_dimensions=frappe.as_json(payload))
		new = old + "-NEW"

		frappe.rename_doc("SD YRP Lot", old, new)

		item = _json("SD YRP Lot Transfer Item", row, "stock_dimensions")["items"][0]
		self.assertEqual(item["dimensions"]["lot"], new)
		self.assertEqual(item["values"], {old: 1})

	def test_received_type_rename_rewrites_values_and_keyed_quantities(self):
		old = "ZZ RT " + frappe.generate_hash(length=6)
		frappe.get_doc({"doctype": "YRP Received Type", "received_type_name": old}).insert()
		deliverable = self.grn_deliverable({"lot": None, "received_type": old})
		keyed = _insert_child(
			"SD YRP Finishing Plan Detail", received_type_json=frappe.as_json({old: 5, "Accepted": 2})
		)
		new = old + " NEW"

		frappe.rename_doc("YRP Received Type", old, new)

		self.assertEqual(
			_json("SD YRP GRN Deliverable", deliverable, "stock_dimensions")["received_type"], new
		)
		self.assertEqual(
			_json("SD YRP Finishing Plan Detail", keyed, "received_type_json"), {new: 5, "Accepted": 2}
		)
