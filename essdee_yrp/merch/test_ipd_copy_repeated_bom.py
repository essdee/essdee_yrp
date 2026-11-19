import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.ipd_ui import duplicate_ipd
from essdee_yrp.merch import ipd_workspace as workspace
from essdee_yrp.merch.ipd.fields import DOCTYPE
from essdee_yrp.merch.ipd_test_support import rolled_back


def find_ipd_with_repeated_mapped_bom_item():
	rows = frappe.db.sql(
		f"""
		select bom.parent
		from `tabYRP Item BOM` bom
		join `tab{DOCTYPE}` ipd on ipd.name = bom.parent
		where bom.parenttype = %s and bom.based_on_attribute_mapping = 1
			and ifnull(bom.attribute_mapping, '') != '' and ifnull(ipd.is_cloth_item, 0) = 0
		group by bom.parent, bom.item
		having count(*) > 1
		order by ipd.modified desc
		limit 1
		""",
		(DOCTYPE,),
	)
	return rows[0][0] if rows else None


class TestIpdCopyRepeatedBom(UnitTestCase):
	"""A BOM item repeated on mapped rows (e.g. Inner Elastic per size group) survives every copy path."""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.source = find_ipd_with_repeated_mapped_bom_item()
		if not self.source:
			self.skipTest("An IPD with a BOM item repeated on mapped rows is required")
		self.source_bom = frappe.get_doc(DOCTYPE, self.source).item_bom

	def assert_bom_copied(self, name):
		copied = frappe.get_doc(DOCTYPE, name).item_bom
		self.assertEqual(
			[(row.item, row.based_on_attribute_mapping) for row in copied],
			[(row.item, row.based_on_attribute_mapping) for row in self.source_bom],
		)
		source_mappings = {row.attribute_mapping for row in self.source_bom if row.attribute_mapping}
		copied_mappings = [row.attribute_mapping for row in copied if row.attribute_mapping]
		self.assertEqual(len(set(copied_mappings)), len(source_mappings))
		self.assertFalse(set(copied_mappings) & source_mappings)

	def test_duplicate_ipd(self):
		with rolled_back("repeated_bom_duplicate"):
			self.assert_bom_copied(duplicate_ipd(self.source))

	def test_new_version_copy(self):
		with rolled_back("repeated_bom_new_version"):
			sections = ["cutting", "accessories", "processes"]
			self.assert_bom_copied(workspace.copy_ipd(self.source, "QA-TP", "QA-P", sections)["name"])

	def test_editor_duplicate_save(self):
		with rolled_back("repeated_bom_editor_duplicate"):
			payload = workspace.save_ipd({"tech_pack_version": "QA-DUP"}, duplicate_from=self.source)
			self.assert_bom_copied(payload["record"]["name"])

	def test_repeated_unmapped_item_is_still_rejected(self):
		with rolled_back("repeated_bom_unmapped"):
			doc = frappe.get_doc(DOCTYPE, duplicate_ipd(self.source))
			repeated = next(
				row for row in doc.item_bom if [other.item for other in doc.item_bom].count(row.item) > 1
			)
			for row in doc.item_bom:
				if row.item == repeated.item:
					row.based_on_attribute_mapping = 0
			with self.assertRaisesRegex(frappe.ValidationError, f"Duplicate Item in BOM {repeated.item}"):
				doc.save()
