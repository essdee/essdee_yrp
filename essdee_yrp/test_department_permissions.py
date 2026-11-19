import json
from pathlib import Path
from unittest import TestCase

import frappe
from frappe.tests import IntegrationTestCase

CUSTOM_DOCPERMS = Path(__file__).parent / "fixtures" / "custom_docperm.json"


class TestDepartmentPermissionFixture(TestCase):
	"""Department Custom DocPerm rows replace the standard ones, so they must keep them."""

	def _department_rows(self):
		with CUSTOM_DOCPERMS.open() as source:
			return {row["role"]: row for row in json.load(source) if row["parent"] == "Department"}

	def test_all_role_can_read_department(self):
		row = self._department_rows()["All"]
		self.assertEqual((row["read"], row["write"], row["create"], row["delete"]), (1, 0, 0, 0))

	def test_standard_department_roles_keep_full_access(self):
		rows = self._department_rows()
		for role in ("HR User", "HR Manager", "Academics User"):
			with self.subTest(role=role):
				row = rows[role]
				self.assertEqual((row["read"], row["write"], row["create"], row["delete"]), (1, 1, 1, 1))

	def test_department_is_exported_by_custom_docperm_fixture(self):
		from essdee_yrp import hooks

		fixture = next(item for item in hooks.fixtures if item.get("dt") == "Custom DocPerm")
		self.assertIn("Department", fixture["filters"][0][2])

	def test_system_manager_can_manage_department(self):
		row = self._department_rows()["System Manager"]
		self.assertEqual((row["read"], row["write"], row["create"], row["delete"]), (1, 1, 1, 1))


class TestSystemManagerEditsDepartmentUsers(IntegrationTestCase):
	"""A System Manager without HR roles adds and removes Department users in Desk."""

	def setUp(self):
		with CUSTOM_DOCPERMS.open() as source:
			row = next(
				r for r in json.load(source) if r["parent"] == "Department" and r["role"] == "System Manager"
			)
		if not frappe.db.exists("Custom DocPerm", row["name"]):
			frappe.get_doc(row).insert(ignore_permissions=True)
		frappe.clear_cache(doctype="Department")
		self.user = self._system_manager_only_user()
		self.department = frappe.get_doc(
			{"doctype": "Department", "department_name": f"_Test Dept Users {frappe.generate_hash(length=8)}"}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_cache(doctype="Department")

	def _system_manager_only_user(self):
		email = f"_test_dept_sm_{frappe.generate_hash(length=8)}@example.com"
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Dept SM", "send_welcome_email": 0}
		)
		user.append("roles", {"role": "System Manager"})
		return user.insert(ignore_permissions=True).name

	def test_add_and_remove_department_user(self):
		frappe.set_user(self.user)
		department = frappe.get_doc("Department", self.department.name)
		self.assertTrue(department.has_permission("write"))
		department.append("department_users", {"user": "Administrator"})
		department.save()
		self.assertEqual(
			frappe.get_all("YRP Department User", {"parent": department.name}, pluck="user"),
			["Administrator"],
		)
		department.reload()
		department.set("department_users", [])
		department.save()
		self.assertFalse(frappe.get_all("YRP Department User", {"parent": department.name}))
