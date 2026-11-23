import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.api.rename import get_rename_status


class TestRenameStatus(IntegrationTestCase):
	def setUp(self):
		self.old = frappe.get_doc({"doctype": "ToDo", "description": "rename status"}).insert().name

	def test_running_while_old_name_still_exists(self):
		status = get_rename_status("ToDo", self.old, self.old + "-new")
		self.assertEqual(status["status"], "running")
		self.assertTrue(status["checked_at"])

	def test_done_once_new_name_exists_and_old_is_gone(self):
		since = get_rename_status("ToDo", self.old, "x")["checked_at"]
		frappe.rename_doc("ToDo", self.old, self.old + "-new", force=True)
		status = get_rename_status("ToDo", self.old, self.old + "-new", since)
		self.assertEqual((status["status"], status["name"]), ("done", self.old + "-new"))

	def test_failed_job_comment_after_since_is_reported(self):
		since = get_rename_status("ToDo", self.old, "x")["checked_at"]
		frappe.get_doc("ToDo", self.old).add_comment(
			"Comment", "Action Failed<br><br><b>Name</b> already exists"
		)
		status = get_rename_status("ToDo", self.old, self.old + "-new", since)
		self.assertEqual((status["status"], status["error"]), ("failed", "Name already exists"))

	def test_requires_read_permission(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				get_rename_status("ToDo", self.old, "x")
		finally:
			frappe.set_user("Administrator")
