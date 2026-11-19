from unittest.mock import patch

import frappe
from frappe import _dict
from frappe.tests import IntegrationTestCase

from essdee_yrp import production_order_workflow
from essdee_yrp.production_order_workflow import (
	PPO_DRAFT_STATUS,
	PPO_REQUEST_STATUS,
	_validate_ppo_submission,
	get_ppo_approver_roles,
	is_fg_item,
	onload,
	require_ppo_approver,
	user_can_submit_ppo_directly,
)
from essdee_yrp.sales import web_workspace

FG_ITEM = "_Test PPO FG Item"
LINKED_ITEM = "_Test PPO Linked Item"
NON_FG_ITEM = "_Test PPO Non FG Item"
MERCH_USER = "Merch User"
MERCH_MANAGER = "Merch Manager"
PLANNER = "Production Planner"


class TestPpoApproverRoles(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for name, item in ((FG_ITEM, None), ("_Test PPO FG Linked", LINKED_ITEM)):
			frappe.get_doc(
				{"doctype": "SD YRP FG Item Master", "name1": name, "uid": name, "item": item}
			).db_insert()

	def setUp(self):
		for fieldname, role in {
			"merch_user_role": MERCH_USER,
			"merchandising_manager_role": MERCH_MANAGER,
			"production_planner_role": PLANNER,
		}.items():
			frappe.db.set_single_value("SD YRP MRP Settings", fieldname, role)

	def assert_allowed(self, item, *roles):
		with patch.object(production_order_workflow.frappe, "get_roles", return_value=list(roles)):
			require_ppo_approver(item, "approve")

	def assert_rejected(self, item, *roles, message):
		with patch.object(production_order_workflow.frappe, "get_roles", return_value=list(roles)):
			with self.assertRaisesRegex(frappe.PermissionError, message):
				require_ppo_approver(item, "approve")

	def test_fg_item_matches_by_name_or_item_link(self):
		self.assertTrue(is_fg_item(FG_ITEM))
		self.assertTrue(is_fg_item(LINKED_ITEM))
		self.assertFalse(is_fg_item(NON_FG_ITEM))
		self.assertFalse(is_fg_item(None))

	def test_fg_item_needs_merch_manager(self):
		self.assertEqual(get_ppo_approver_roles(FG_ITEM), {MERCH_MANAGER})
		self.assert_rejected(
			FG_ITEM, PLANNER, message="is in the FG Item Master, so only the Merch Manager role"
		)
		self.assert_rejected(LINKED_ITEM, PLANNER, message="only the Merch Manager role")
		self.assert_allowed(FG_ITEM, MERCH_MANAGER)

	def test_non_fg_item_allows_planner_or_merch_manager(self):
		self.assertEqual(get_ppo_approver_roles(NON_FG_ITEM), {PLANNER, MERCH_MANAGER})
		self.assert_allowed(NON_FG_ITEM, PLANNER)
		self.assert_allowed(NON_FG_ITEM, MERCH_MANAGER)

	def test_merch_user_alone_cannot_approve(self):
		self.assert_rejected(FG_ITEM, MERCH_USER, message="only the Merch Manager role")
		self.assert_rejected(
			NON_FG_ITEM,
			MERCH_USER,
			message="is not in the FG Item Master, so only the Merch Manager or Production Planner role",
		)

	def test_missing_role_setting_fails_loudly(self):
		frappe.db.set_single_value("SD YRP MRP Settings", "merchandising_manager_role", None)
		with patch.object(production_order_workflow.frappe, "get_roles", return_value=[MERCH_MANAGER]):
			with self.assertRaisesRegex(frappe.ValidationError, "Configure its PPO approver role"):
				require_ppo_approver(FG_ITEM, "approve")

	def test_endpoints_check_the_production_order_item_before_loading(self):
		get_value = frappe.db.get_value

		def item_of_order(doctype, *args, **kwargs):
			if doctype == "YRP Production Order":
				return FG_ITEM
			return get_value(doctype, *args, **kwargs)

		with (
			patch.object(production_order_workflow.frappe, "get_roles", return_value=[PLANNER]),
			patch.object(production_order_workflow.frappe.db, "get_value", side_effect=item_of_order),
			patch.object(production_order_workflow, "lock_production_orders") as lock,
		):
			for action in (
				lambda: production_order_workflow.approve_ppo("PPO-FG"),
				lambda: production_order_workflow.request_ppo_changes("PPO-FG", "Fix sizes"),
			):
				with self.assertRaisesRegex(frappe.PermissionError, "FG Item Master"):
					action()
		lock.assert_not_called()

	def test_submit_guard_and_onload_follow_the_item_rule(self):
		doc = _dict(
			item=FG_ITEM,
			status=PPO_REQUEST_STATUS,
			docstatus=0,
			flags=_dict(),
			name="PPO-FG",
			production_order_details=[],
			production_ordered_details=[],
		)
		doc.set_onload = lambda key, value: doc.setdefault("onload", {}).update({key: value})
		with patch.object(production_order_workflow.frappe, "get_roles", return_value=[PLANNER]):
			with self.assertRaises(frappe.PermissionError):
				_validate_ppo_submission(doc)
			with patch.object(production_order_workflow, "get_ppo_action_roles", return_value=set()):
				onload(doc)
		self.assertFalse(doc.onload["can_approve_ppo"])

		doc.item = NON_FG_ITEM
		with patch.object(production_order_workflow.frappe, "get_roles", return_value=[PLANNER]):
			_validate_ppo_submission(doc)
			with patch.object(production_order_workflow, "get_ppo_action_roles", return_value=set()):
				onload(doc)
		self.assertTrue(doc.onload["can_approve_ppo"])

	def draft(self, item):
		doc = _dict(
			item=item,
			status=PPO_DRAFT_STATUS,
			docstatus=0,
			flags=_dict(),
			name="PPO-DRAFT",
			production_order_details=[],
			production_ordered_details=[],
		)
		doc.set_onload = lambda key, value: doc.setdefault("onload", {}).update({key: value})
		return doc

	def test_planner_submits_non_fg_draft_directly(self):
		doc = self.draft(NON_FG_ITEM)
		with patch.object(production_order_workflow.frappe, "get_roles", return_value=[PLANNER]):
			self.assertTrue(user_can_submit_ppo_directly(NON_FG_ITEM))
			_validate_ppo_submission(doc)
			with patch.object(production_order_workflow, "get_ppo_action_roles", return_value={PLANNER}):
				onload(doc)
		self.assertTrue(doc.flags.ppo_submitted_directly)
		self.assertTrue(doc.onload["can_submit_ppo_directly"])
		self.assertFalse(doc.onload["can_request_ppo_approval"])

	def test_fg_draft_or_non_planner_must_request_approval(self):
		for item, role in ((FG_ITEM, PLANNER), (NON_FG_ITEM, MERCH_MANAGER), (NON_FG_ITEM, MERCH_USER)):
			with self.subTest(item=item, role=role):
				doc = self.draft(item)
				with patch.object(production_order_workflow.frappe, "get_roles", return_value=[role]):
					self.assertFalse(user_can_submit_ppo_directly(item))
					with self.assertRaisesRegex(frappe.ValidationError, "Send the Production Order for PPO approval"):
						_validate_ppo_submission(doc)
					with patch.object(production_order_workflow, "get_ppo_action_roles", return_value={role}):
						onload(doc)
				self.assertFalse(doc.flags.get("ppo_submitted_directly"))
				self.assertFalse(doc.onload["can_submit_ppo_directly"])
				self.assertTrue(doc.onload["can_request_ppo_approval"])

	def test_web_submit_action_follows_direct_submit_flag(self):
		permissions = dict.fromkeys(
			("can_read", "can_create", "can_write", "can_delete", "can_submit", "can_cancel", "can_print"), True
		)
		doc = _dict(docstatus=0, status=PPO_DRAFT_STATUS)
		for can_submit_directly in (True, False):
			onload_flags = {
				"can_manage_production_order": True,
				"can_submit_ppo_directly": can_submit_directly,
				"can_request_ppo_approval": not can_submit_directly,
			}
			actions = web_workspace._production_order_actions(doc, permissions, onload_flags)
			self.assertEqual(actions["submit_ppo"]["allowed"], can_submit_directly)
			self.assertEqual(actions["request_ppo_approval"]["allowed"], not can_submit_directly)
