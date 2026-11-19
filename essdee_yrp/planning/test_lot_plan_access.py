from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.planning import dashboard_workspace, lot_workspace


def read_only(*allowed):
	def has_permission(doctype, ptype="read", throw=False, **kwargs):
		if doctype in allowed:
			return True
		if throw:
			raise frappe.PermissionError
		return False

	return has_permission


class TestLotPlanAccess(TestCase):
	def test_access_follows_plan_doctype_read(self):
		cases = {
			(): {"ccr": False, "ocr": False},
			("SD YRP Cutting Plan",): {"ccr": True, "ocr": False},
			("SD YRP Finishing Plan",): {"ccr": False, "ocr": True},
			("SD YRP Cutting Plan", "SD YRP Finishing Plan"): {"ccr": True, "ocr": True},
		}
		for allowed, expected in cases.items():
			with patch.object(lot_workspace.frappe, "has_permission", side_effect=read_only(*allowed)):
				self.assertEqual(lot_workspace.get_plan_access(), expected, allowed)

	def test_plan_lists_require_plan_read(self):
		with patch.object(lot_workspace.frappe, "has_permission", side_effect=read_only()), patch.object(
			lot_workspace.frappe, "get_list"
		) as get_list:
			for call in (lot_workspace.get_lot_cutting_plans, lot_workspace.get_lot_finishing_plans):
				with self.assertRaises(frappe.PermissionError):
					call("LOT-1")
		get_list.assert_not_called()

	def test_plan_lists_skip_cancelled_plans_of_the_lot(self):
		with patch.object(
			lot_workspace.frappe, "has_permission", side_effect=read_only("SD YRP Cutting Plan", "SD YRP Finishing Plan")
		), patch.object(lot_workspace.frappe, "get_list", return_value=[{"name": "CP-1"}]) as get_list:
			self.assertEqual(lot_workspace.get_lot_cutting_plans("LOT-1"), [{"name": "CP-1"}])
			lot_workspace.get_lot_finishing_plans("LOT-1")
		doctypes = [call.args[0] for call in get_list.call_args_list]
		self.assertEqual(doctypes, ["SD YRP Cutting Plan", "SD YRP Finishing Plan"])
		for call in get_list.call_args_list:
			self.assertEqual(call.kwargs["filters"], [["lot", "=", "LOT-1"], ["docstatus", "!=", 2]])

	def test_lot_workspace_and_tracking_carry_plan_access(self):
		access = {"ccr": True, "ocr": False}
		with patch.object(lot_workspace, "get_plan_access", return_value=access), patch.object(
			lot_workspace.purchase_lot_workspace, "get_lot_workspace", return_value={"name": "LOT-1"}
		), patch.object(lot_workspace, "LotFlowData"), patch.object(
			lot_workspace.merch_lot_workspace, "get_record_facts", return_value=[]
		):
			self.assertEqual(lot_workspace.get_lot_workspace("LOT-1")["plan_access"], access)
		with patch.object(dashboard_workspace, "get_plan_access", return_value=access), patch.object(
			dashboard_workspace, "require_dashboard_access"
		), patch.object(dashboard_workspace.tracking, "get_tracking_data", return_value={"lots": []}):
			self.assertEqual(dashboard_workspace.get_tracking(["PPO-1"], [])["plan_access"], access)
