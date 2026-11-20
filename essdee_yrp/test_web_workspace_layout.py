import json

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import hooks
from essdee_yrp.ui_config import get_config_for_boot
from essdee_yrp.web_workspace_layout import (
	OVERRIDE_DOCTYPE,
	WORKSPACE_EXPERIENCE,
	delete_layout,
	get_builder_data,
	get_department_workspaces,
	reset_department_override,
	save_department_override,
	save_layout,
)

TITLE = "Test Builder Workspace"
CLERK = "workspace-builder-clerk@example.com"
SECTIONS = [
	{"label": "Orders", "cards": ["merch:lots", "planning:lots"]},
	{"label": "Buying", "cards": ["purchase:purchase_orders"]},
]


class TestWebWorkspaceLayout(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(self.remove_layouts)

	def remove_layouts(self):
		frappe.set_user("Administrator")
		for user in (CLERK, "Administrator"):
			if frappe.db.get_value("YRP UI Preference", user, "layout") in (TITLE, f"{TITLE} Renamed"):
				frappe.delete_doc("YRP UI Preference", user, ignore_permissions=True, force=True)
		for name in (TITLE, f"{TITLE} Renamed"):
			if frappe.db.exists("YRP UI Layout", name):
				frappe.delete_doc("YRP UI Layout", name, ignore_permissions=True, force=True)

	def make_clerk(self):
		if not frappe.db.exists("User", CLERK):
			frappe.get_doc(
				{"doctype": "User", "email": CLERK, "first_name": "Builder Clerk", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		return CLERK

	def test_only_system_managers_can_call_the_builder(self):
		frappe.set_user(self.make_clerk())
		for call in (
			lambda: get_builder_data(),
			lambda: save_layout(TITLE, json.dumps(SECTIONS)),
			lambda: delete_layout(TITLE),
		):
			with self.assertRaises(frappe.PermissionError):
				call()

	def test_save_creates_a_workspace_registered_experience_layout(self):
		result = save_layout(TITLE, json.dumps(SECTIONS))

		layout = frappe.get_doc("YRP UI Layout", result["name"])
		self.assertEqual(layout.name, TITLE)
		self.assertEqual(layout.render_mode, "Registered Experience")
		self.assertEqual(layout.experience_key, WORKSPACE_EXPERIENCE)
		props = json.loads(layout.config)["experience_props"]
		self.assertEqual(props, {"workspace": {"title": TITLE, "sections": SECTIONS}})
		builder_layouts = {row["name"]: row for row in get_builder_data()["layouts"]}
		self.assertEqual(builder_layouts[TITLE]["sections"], SECTIONS)

	def test_save_updates_and_renames_an_existing_builder_layout(self):
		save_layout(TITLE, json.dumps(SECTIONS))

		renamed = save_layout(f"{TITLE} Renamed", json.dumps(SECTIONS[:1]), original_name=TITLE)

		self.assertEqual(renamed["name"], f"{TITLE} Renamed")
		self.assertFalse(frappe.db.exists("YRP UI Layout", TITLE))
		config = json.loads(frappe.db.get_value("YRP UI Layout", renamed["name"], "config"))
		self.assertEqual(config["experience_props"]["workspace"]["sections"], SECTIONS[:1])

	def test_invalid_cards_and_sections_are_rejected(self):
		for sections in (
			[{"label": "Orders", "cards": ["merch:no_such_card"]}],
			[{"label": "Orders", "cards": ["merch:lots", "merch:lots"]}],
			[{"label": "", "cards": ["merch:lots"]}],
			[{"label": "Orders", "cards": []}],
			[],
		):
			with self.subTest(sections=sections), self.assertRaises(frappe.ValidationError):
				save_layout(TITLE, json.dumps(sections))
		self.assertFalse(frappe.db.exists("YRP UI Layout", TITLE))

	def test_names_of_built_in_and_other_layouts_are_rejected(self):
		for name in ("Premium White", "Cutting", "Production Planner"):
			with self.subTest(name=name), self.assertRaises(frappe.ValidationError):
				save_layout(name, json.dumps(SECTIONS))
		self.assertIn("Premium White", get_builder_data()["reserved_names"])
		save_layout(TITLE, json.dumps(SECTIONS))
		with self.assertRaises(frappe.ValidationError):
			save_layout(TITLE, json.dumps(SECTIONS))

	def test_delete_removes_only_builder_layouts(self):
		save_layout(TITLE, json.dumps(SECTIONS))
		with self.assertRaises(frappe.ValidationError):
			delete_layout("Cutting")

		delete_layout(TITLE)

		self.assertFalse(frappe.db.exists("YRP UI Layout", TITLE))
		self.assertTrue(frappe.db.exists("YRP UI Layout", "Cutting"))

	def test_boot_ui_config_carries_the_workspace_layout(self):
		save_layout(TITLE, json.dumps(SECTIONS))
		frappe.get_doc({"doctype": "YRP UI Preference", "user": "Administrator", "layout": TITLE}).insert(
			ignore_permissions=True
		)

		boot = get_config_for_boot()

		self.assertEqual(boot["meta"]["render_mode"], "Registered Experience")
		self.assertEqual(boot["meta"]["experience_key"], WORKSPACE_EXPERIENCE)
		self.assertEqual(boot["meta"]["department_layout"], TITLE)
		self.assertEqual(boot["config"]["experience_props"]["workspace"]["sections"], SECTIONS)


OVERRIDE_LAYOUT = "HR"
OVERRIDE_SECTIONS = [
	{"label": "People", "cards": ["hr:reports", "merch:lots"]},
]


class TestDepartmentLayoutOverride(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(self.remove_override)
		self.remove_override()

	def remove_override(self):
		if frappe.db.exists(OVERRIDE_DOCTYPE, OVERRIDE_LAYOUT):
			frappe.delete_doc(OVERRIDE_DOCTYPE, OVERRIDE_LAYOUT, ignore_permissions=True, force=True)

	def department_layout(self, name):
		return next(row for row in get_builder_data()["department_layouts"] if row["name"] == name)

	def test_only_system_managers_can_override_or_reset(self):
		if not frappe.db.exists("User", CLERK):
			frappe.get_doc(
				{"doctype": "User", "email": CLERK, "first_name": "Builder Clerk", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.set_user(CLERK)
		for call in (
			lambda: save_department_override(OVERRIDE_LAYOUT, json.dumps(OVERRIDE_SECTIONS)),
			lambda: reset_department_override(OVERRIDE_LAYOUT),
		):
			with self.assertRaises(frappe.PermissionError):
				call()

	def test_builder_lists_every_built_in_department_layout_with_its_default_workspaces(self):
		layouts = get_builder_data()["department_layouts"]

		self.assertEqual(len(layouts), 16)
		hr = self.department_layout(OVERRIDE_LAYOUT)
		self.assertEqual(hr["experience_key"], "hr")
		self.assertEqual(hr["workspaces"], ["bill_tracking", "reports"])
		self.assertIsNone(hr["sections"])

	def test_override_saves_outside_the_layout_record_and_reset_removes_it(self):
		config = frappe.db.get_value("YRP UI Layout", OVERRIDE_LAYOUT, "config")

		save_department_override(OVERRIDE_LAYOUT, json.dumps(OVERRIDE_SECTIONS))

		self.assertEqual(frappe.db.get_value("YRP UI Layout", OVERRIDE_LAYOUT, "config"), config)
		self.assertEqual(self.department_layout(OVERRIDE_LAYOUT)["sections"], OVERRIDE_SECTIONS)
		self.assertEqual(
			get_department_workspaces()["hr"], {"layout": OVERRIDE_LAYOUT, "sections": OVERRIDE_SECTIONS}
		)
		save_department_override(OVERRIDE_LAYOUT, json.dumps(OVERRIDE_SECTIONS[:1]))
		self.assertEqual(frappe.db.count(OVERRIDE_DOCTYPE, {"layout": OVERRIDE_LAYOUT}), 1)

		reset_department_override(OVERRIDE_LAYOUT)

		self.assertFalse(frappe.db.exists(OVERRIDE_DOCTYPE, OVERRIDE_LAYOUT))
		self.assertNotIn("hr", get_department_workspaces())

	def test_only_built_in_department_layouts_take_an_override(self):
		for name in ("Premium White", "Unknown Layout"):
			with self.subTest(name=name), self.assertRaises(frappe.ValidationError):
				save_department_override(name, json.dumps(OVERRIDE_SECTIONS))
		with self.assertRaises(frappe.ValidationError):
			save_department_override(OVERRIDE_LAYOUT, json.dumps([{"label": "X", "cards": ["hr:nope"]}]))

	def test_boot_carries_department_overrides_and_fixtures_never_export_them(self):
		save_department_override(OVERRIDE_LAYOUT, json.dumps(OVERRIDE_SECTIONS))

		boot = get_config_for_boot()

		self.assertEqual(boot["department_workspaces"]["hr"]["sections"], OVERRIDE_SECTIONS)
		fixture_doctypes = {row["dt"] if isinstance(row, dict) else row for row in hooks.fixtures}
		self.assertNotIn(OVERRIDE_DOCTYPE, fixture_doctypes)
