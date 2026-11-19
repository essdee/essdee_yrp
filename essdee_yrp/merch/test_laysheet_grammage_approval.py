import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.merch.laysheet_grammage_approval import approve_laysheets, get_pending_laysheets
from essdee_yrp.test_cls_grammage_approval import make_user

DOCTYPE = "SD YRP Cutting LaySheet"
APPROVER = "cls.grammage.web.approver@test.local"
READER = "cls.grammage.web.reader@test.local"


class TestLaySheetGrammageApprovalCard(IntegrationTestCase):
	"""Merch card listing and approving Approval Pending Cutting LaySheets."""

	def setUp(self):
		self.laysheet = frappe.db.get_value(
			DOCTYPE,
			{"status": "Approval Pending", "docstatus": 0, "cutting_plan": ["is", "set"]},
			["name", "cutting_plan", "lot", "item"],
			as_dict=True,
		)
		if not self.laysheet:
			self.skipTest("No Approval Pending Cutting LaySheet on this site")
		self.work_order = frappe.db.get_value("SD YRP Cutting Plan", self.laysheet.cutting_plan, "work_order")
		settings = frappe.get_single("SD YRP MRP Settings")
		if "Merch Manager" not in {row.role for row in settings.cls_grammage_approval_roles}:
			settings.append("cls_grammage_approval_roles", {"role": "Merch Manager"})
			settings.save(ignore_permissions=True)
		make_user(APPROVER, ["Merch User", "Merch Manager"])
		make_user(READER, ["Merch User"])

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_lists_only_pending_laysheets_with_plan_details(self):
		frappe.set_user(READER)
		result = get_pending_laysheets()
		self.assertFalse(result["can_approve"])
		names = [row.name for row in result["rows"]]
		self.assertIn(self.laysheet.name, names)
		statuses = set(frappe.get_all(DOCTYPE, filters={"name": ["in", names]}, pluck="status"))
		self.assertEqual(statuses, {"Approval Pending"})
		row = next(row for row in result["rows"] if row.name == self.laysheet.name)
		self.assertEqual(
			(row.lot, row.cutting_plan, row.work_order),
			(self.laysheet.lot, self.laysheet.cutting_plan, self.work_order),
		)
		self.assertEqual(
			row.item_name, frappe.db.get_value("Item", self.laysheet.item, "item_name") or self.laysheet.item
		)
		self.assertIn("required_pcs_weight", row)
		self.assertIn("lay_no", row)
		self.assertIn("posting_date", row)
		self.assertIn("piece_weight", row)

	def test_link_filters_narrow_the_list(self):
		filtered = get_pending_laysheets(
			lot=self.laysheet.lot, cutting_plan=self.laysheet.cutting_plan, item=self.laysheet.item
		)
		self.assertIn(self.laysheet.name, [row.name for row in filtered["rows"]])
		self.assertTrue(all(row.cutting_plan == self.laysheet.cutting_plan for row in filtered["rows"]))
		self.assertEqual(get_pending_laysheets(lot="__no_such_lot__")["rows"], [])
		self.assertEqual(get_pending_laysheets(work_order="__no_such_work_order__")["rows"], [])
		if self.work_order:
			by_work_order = get_pending_laysheets(work_order=self.work_order)["rows"]
			self.assertIn(self.laysheet.name, [row.name for row in by_work_order])

	def test_user_without_approval_role_cannot_approve(self):
		frappe.set_user(READER)
		with self.assertRaises(frappe.PermissionError):
			approve_laysheets([self.laysheet.name])
		self.assertEqual(frappe.db.get_value(DOCTYPE, self.laysheet.name, "status"), "Approval Pending")

	def test_bulk_approve_reports_each_failure_and_drops_approved_rows(self):
		not_pending = frappe.db.get_value(DOCTYPE, {"status": ["!=", "Approval Pending"]}, "name")
		frappe.set_user(APPROVER)
		self.assertTrue(get_pending_laysheets()["can_approve"])
		names = [self.laysheet.name, not_pending, "CLS-DOES-NOT-EXIST"]
		result = approve_laysheets(frappe.as_json([name for name in names if name]))
		self.assertEqual(result["approved"], [self.laysheet.name])
		failed = {row["name"]: row["error"] for row in result["failed"]}
		self.assertIn("CLS-DOES-NOT-EXIST", failed)
		if not_pending:
			self.assertIn("not pending approval", failed[not_pending])
		self.assertEqual(
			frappe.db.get_value(DOCTYPE, self.laysheet.name, ["status", "approved_by"]),
			("Bundles Generated", APPROVER),
		)
		self.assertNotIn(self.laysheet.name, [row.name for row in get_pending_laysheets()["rows"]])
