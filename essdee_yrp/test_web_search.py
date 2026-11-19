from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp import web_search


class TestDepartmentCapabilities(TestCase):
	def test_returns_every_source_keyed_by_name(self):
		sources = {
			"cutting": lambda: {"cutting-plans": {"can_read": True}},
			"merch": lambda: {"sections": {}},
		}
		with patch.dict(web_search.CAPABILITY_SOURCES, sources, clear=True):
			self.assertEqual(
				web_search.get_department_capabilities(),
				{"cutting": {"cutting-plans": {"can_read": True}}, "merch": {"sections": {}}},
			)

	def test_shares_one_report_access_scope(self):
		scopes = []

		def source():
			scopes.append(frappe.local.report_access)
			return {}

		with patch.dict(web_search.CAPABILITY_SOURCES, {"first": source, "second": source}, clear=True):
			web_search.get_department_capabilities()
		self.assertIsNotNone(scopes[0])
		self.assertIs(scopes[0], scopes[1])

	def test_covers_every_department_capability_endpoint(self):
		self.assertEqual(
			set(web_search.CAPABILITY_SOURCES),
			{
				"cutting",
				"cutting_reports",
				"fabric_store",
				"cut_panel_store",
				"sewing",
				"finishing",
				"quality",
				"merch",
				"purchase",
				"merch_purchase",
				"merch_pd",
				"sales",
				"planning",
				"pd",
				"accounts",
				"hr",
			},
		)

	def test_a_limited_user_gets_a_payload_without_errors(self):
		frappe.set_user("Guest")
		try:
			payload = web_search.get_department_capabilities()
		finally:
			frappe.set_user("Administrator")
		self.assertFalse(payload["merch"]["sections"]["lots"]["can_read"])
