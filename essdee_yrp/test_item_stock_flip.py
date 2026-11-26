import frappe
from erpnext.controllers.item_variant import create_variant
from frappe.tests import IntegrationTestCase

ATTRIBUTE = "_Test Stock Flip Size"
VALUES = ("S", "M")
DOCUMENT_ROWS = (
	("Purchase Invoice Item", "Purchase Invoice"),
	("Purchase Order Item", "Purchase Order"),
	("Material Request Item", "Material Request"),
	("Sales Invoice Item", "Sales Invoice"),
	("Delivery Note Item", "Delivery Note"),
	("Purchase Receipt Item", "Purchase Receipt"),
	("Stock Entry Detail", "Stock Entry"),
	("Sales Order Item", "Sales Order"),
)


def make_item(**values):
	return frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": f"_Test Stock Flip {frappe.generate_hash(length=8)}",
			"item_group": "All Item Groups",
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"gst_hsn_code": frappe.db.get_value("GST HSN Code", {}, "name"),
			**values,
		}
	).insert(ignore_permissions=True)


def insert_row(doctype, **values):
	frappe.get_doc({"doctype": doctype, **values}).db_insert()


def add_submitted_row(doctype, parenttype, item_code):
	insert_row(
		doctype,
		parenttype=parenttype,
		parentfield="items",
		parent=f"_Test {frappe.generate_hash(length=8)}",
		item_code=item_code,
		docstatus=1,
	)


def add_full_history(item_code):
	for doctype, parenttype in DOCUMENT_ROWS:
		add_submitted_row(doctype, parenttype, item_code)
	insert_row(
		"Stock Ledger Entry",
		item_code=item_code,
		voucher_type="Stock Entry",
		voucher_no=f"_Test {frappe.generate_hash(length=8)}",
		is_cancelled=0,
	)
	insert_row(
		"YRP Bin",
		item_code=item_code,
		warehouse=frappe.db.get_value("Warehouse", {"is_group": 0}),
		actual_qty=5,
	)


def set_stock_item(item_code, value):
	item = frappe.get_doc("Item", item_code)
	item.is_stock_item = value
	item.save(ignore_permissions=True)


class TestItemStockFlip(IntegrationTestCase):
	def test_any_history_does_not_block_enabling_maintain_stock(self):
		item = make_item()
		add_full_history(item.name)
		set_stock_item(item.name, 1)
		self.assertEqual(frappe.db.get_value("Item", item.name, "is_stock_item"), 1)

	def test_documents_without_stock_do_not_block_disabling_maintain_stock(self):
		item = make_item(is_stock_item=1)
		for doctype, parenttype in DOCUMENT_ROWS:
			if doctype != "Stock Entry Detail":
				add_submitted_row(doctype, parenttype, item.name)
		set_stock_item(item.name, 0)
		self.assertEqual(frappe.db.get_value("Item", item.name, "is_stock_item"), 0)

	def test_disabling_maintain_stock_stays_blocked_by_stock_ledger(self):
		item = make_item(is_stock_item=1)
		insert_row(
			"Stock Ledger Entry",
			item_code=item.name,
			voucher_type="Stock Entry",
			voucher_no=f"_Test {frappe.generate_hash(length=8)}",
			is_cancelled=0,
		)
		with self.assertRaisesRegex(frappe.ValidationError, "Maintain Stock"):
			set_stock_item(item.name, 0)

	def test_disabling_maintain_stock_stays_blocked_by_yrp_stock(self):
		item = make_item(is_stock_item=1)
		insert_row(
			"YRP Bin",
			item_code=item.name,
			warehouse=frappe.db.get_value("Warehouse", {"is_group": 0}),
			actual_qty=5,
		)
		with self.assertRaisesRegex(frappe.ValidationError, "YRP stock exists"):
			set_stock_item(item.name, 0)

	def make_template_with_variants(self):
		if not frappe.db.exists("Item Attribute", ATTRIBUTE):
			frappe.get_doc(
				{
					"doctype": "Item Attribute",
					"attribute_name": ATTRIBUTE,
					"item_attribute_values": [{"attribute_value": value, "abbr": value} for value in VALUES],
				}
			).insert(ignore_permissions=True)
		template = make_item(has_variants=1, attributes=[{"attribute": ATTRIBUTE}])
		variants = [
			create_variant(template.name, {ATTRIBUTE: value}).insert(ignore_permissions=True).name
			for value in VALUES
		]
		return template, variants

	def test_template_save_copies_maintain_stock_off_to_variants_without_stock(self):
		template, (stock_variant, plain_variant) = self.make_template_with_variants()
		set_stock_item(stock_variant, 1)
		add_submitted_row("Purchase Invoice Item", "Purchase Invoice", stock_variant)
		template = frappe.get_doc("Item", template.name)
		template.description = "Edited template"
		template.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Item", stock_variant, "is_stock_item"), 0)
		self.assertEqual(frappe.db.get_value("Item", plain_variant, "is_stock_item"), 0)

	def test_template_flip_reaches_variants_with_history(self):
		template, variants = self.make_template_with_variants()
		for variant in variants:
			add_full_history(variant)
		set_stock_item(template.name, 1)
		self.assertEqual(frappe.db.get_value("Item", template.name, "is_stock_item"), 1)
		for variant in variants:
			self.assertEqual(frappe.db.get_value("Item", variant, "is_stock_item"), 1)
