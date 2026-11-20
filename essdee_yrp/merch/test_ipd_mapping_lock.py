import frappe
from frappe.tests import UnitTestCase
from yrp.yrp.doctype.yrp_item.yrp_item import (
	get_dependent_attribute_details,
	update_dependent_attribute_details,
)

from essdee_yrp.ipd_validations import is_mapping_shared
from essdee_yrp.merch.ipd.fields import DOCTYPE
from essdee_yrp.merch.ipd.mapping_lock import DEPENDENT_MAPPING, ITEM_MAPPING, get_linked_ipds
from essdee_yrp.merch.ipd_test_support import make_user, rolled_back

MERCH_USER = "ipd-mapping-lock@example.com"


class TestIpdMappingLock(UnitTestCase):
	"""Mappings linked from an IPD follow its write permission, not its approval."""

	def setUp(self):
		super().setUp()
		self.name, self.mapping = owned_mapping()
		if not self.name:
			self.skipTest("An approved garment IPD with owned attribute mappings is required")
		self.dependent = frappe.db.get_value(DOCTYPE, self.name, "dependent_attribute_mapping")

	def test_linked_ipds_cover_item_and_dependent_mappings(self):
		self.assertIn(self.name, get_linked_ipds(frappe.get_doc(ITEM_MAPPING, self.mapping)))
		self.assertIn(self.name, get_linked_ipds(frappe.get_doc(DEPENDENT_MAPPING, self.dependent)))

	def test_approved_ipd_allows_mapping_saves_for_writers(self):
		detail = get_dependent_attribute_details(self.dependent)
		with rolled_back("ipd_mapping_lock"):
			frappe.get_doc(ITEM_MAPPING, self.mapping).save()
			update_dependent_attribute_details(self.dependent, frappe.as_json(detail))
			self.assertEqual(frappe.db.get_value(DOCTYPE, self.name, "approval_status"), "Approved")

	def test_user_without_ipd_write_cannot_save_mapping(self):
		with rolled_back("ipd_mapping_lock"):
			make_user(MERCH_USER, ["Merch User"])
			mapping = frappe.get_doc(ITEM_MAPPING, self.mapping)
			frappe.set_user(MERCH_USER)
			try:
				self.assertTrue(frappe.has_permission(ITEM_MAPPING, "write", doc=mapping))
				self.assertFalse(frappe.has_permission(DOCTYPE, "write", doc=self.name))
				with self.assertRaisesRegex(frappe.PermissionError, "need write permission on IPD"):
					mapping.save()
				onload = frappe.get_doc(ITEM_MAPPING, self.mapping)
				onload.run_method("onload")
				self.assertIn("write permission", onload.get_onload().get("ipd_mapping_lock"))
			finally:
				frappe.set_user("Administrator")

	def test_onload_has_no_lock_for_writers_on_approved_ipd(self):
		mapping = frappe.get_doc(DEPENDENT_MAPPING, self.dependent)
		mapping.run_method("onload")
		self.assertEqual(mapping.get_onload().get("ipd_mapping_lock"), "")


def owned_mapping():
	rows = frappe.db.sql(
		"""select ipd.name, a.mapping from `tabYRP Item Production Detail` ipd
		join `tabYRP IPD Item Attribute` a on a.parent = ipd.name and a.parenttype = %s
		where ipd.approval_status = 'Approved' and ipd.is_cloth_item = 0
		and ipd.dependent_attribute_mapping is not null and a.mapping is not null
		order by ipd.modified desc limit 50""",
		DOCTYPE,
		as_dict=True,
	)
	for row in rows:
		if not is_mapping_shared(ITEM_MAPPING, row.mapping, row.name):
			return row.name, row.mapping
	return None, None
