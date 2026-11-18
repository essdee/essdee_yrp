from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.planning import dashboard_workspace
from essdee_yrp.planning.dashboard import dashboard, tracking
from essdee_yrp.planning.dashboard.production_orders import PPO


class TestDashboardEndpointAccess(TestCase):
	def test_every_endpoint_requires_dashboard_read(self):
		calls = (
			lambda: dashboard_workspace.get_dashboard(),
			lambda: dashboard_workspace.get_tracking_options(),
			lambda: dashboard_workspace.get_tracking(["PPO-00044"], []),
			lambda: dashboard_workspace.get_process_detail("F0426-85", "Cutting"),
		)
		with patch.object(dashboard_workspace, "can_read", return_value=False):
			for call in calls:
				with self.assertRaises(frappe.PermissionError):
					call()

	def test_tracking_needs_a_ppo_or_lot(self):
		with patch.object(dashboard_workspace, "can_read", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				dashboard_workspace.get_tracking([], [])

	def test_dashboard_needs_finishing_plan_read_for_dispatch(self):
		with patch.object(
			dashboard_workspace.frappe,
			"has_permission",
			side_effect=lambda doctype, ptype: doctype != "SD YRP Finishing Plan",
		):
			self.assertFalse(dashboard_workspace.has_dashboard_access())


class TestDashboardOpenOnly(TestCase):
	def get_filters(self, call):
		"""{doctype: filters} of every frappe.get_list call made by `call`."""
		seen = {}

		def fake_get_list(doctype, filters=None, **kwargs):
			seen.setdefault(doctype, filters)
			if doctype == PPO:
				return [{"name": "PPO-1", "status": "Open", "delivery_date": None}]
			return []

		with (
			patch("frappe.get_list", side_effect=fake_get_list),
			patch(
				"essdee_yrp.planning.dashboard.tracking.get_ppo_items",
				return_value={"PPO-1": {"item": "", "item_name": ""}},
			),
		):
			call()
		return seen

	def assert_open_only(self, seen):
		self.assertEqual(seen[PPO]["docstatus"], 1)
		self.assertEqual(seen[PPO]["status"], "Open")
		self.assertEqual(seen["SD YRP Lot"]["status"], "Open")

	def test_dashboard_excludes_closed_and_cancelled(self):
		self.assert_open_only(self.get_filters(dashboard.get_dashboard_data))

	def test_tracking_options_exclude_closed_and_cancelled(self):
		self.assert_open_only(self.get_filters(tracking.get_tracking_options))

	def test_tracking_scope_excludes_closed_and_cancelled(self):
		with patch.object(tracking, "authorize_filter_values", side_effect=lambda doctype, values: values):
			self.assert_open_only(self.get_filters(lambda: tracking.get_tracking_data(["PPO-1"], [])))
