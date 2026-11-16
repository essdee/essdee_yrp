"""Fixtures shared by the Time and Action tests."""

import erpnext
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate


class TimeAndActionTestCase(FrappeTestCase):
	"""Rolls back after every test so tests never see each other's records."""

	def tearDown(self):
		frappe.db.rollback()
		frappe.set_user("Administrator")
		frappe.flags.in_time_and_action_update = False


def use_company_holidays(holidays, from_date="2026-01-01", to_date="2027-12-31"):
	"""Point the default Company at a fresh holiday list holding `holidays`."""
	name = f"TA-TEST-{frappe.generate_hash(length=6)}"
	frappe.get_doc(
		{
			"doctype": "Holiday List",
			"holiday_list_name": name,
			"from_date": from_date,
			"to_date": to_date,
			"holidays": [{"holiday_date": day, "description": "Test"} for day in holidays],
		}
	).insert()
	frappe.db.set_value("Company", erpnext.get_default_company(), "default_holiday_list", name)
	return name


def make_action(name, lead_time=1):
	if not frappe.db.exists("SD YRP Action", name):
		frappe.get_doc(
			{
				"doctype": "SD YRP Action",
				"__newname": name,
				"lead_time": lead_time,
				"department": department(),
			}
		).insert(set_name=name)
	return name


def department():
	return frappe.db.get_value("Department", {"is_group": 0}, "name") or frappe.db.get_value("Department", {})


def make_master(steps, dependencies):
	"""`steps`: [(action, lead_time)], `dependencies`: {action: [depends_on]}."""
	for action, lead_time in steps:
		make_action(action, lead_time)
	doc = frappe.get_doc(
		{
			"doctype": "SD YRP Action Master",
			"description": "TA-TEST master",
			"details": [
				{"action": action, "lead_time": lead_time, "department": department()}
				for action, lead_time in steps
			],
			"action_master_dependent_details": [
				{"action": action, "dependent_action": dependency}
				for action, depends_on in dependencies.items()
				for dependency in depends_on
			],
		}
	)
	doc.insert()
	return doc


def make_lot(production_order=None):
	item = frappe.db.get_value("SD YRP Lot", {"item": ["is", "set"]}, "item")
	doc = frappe.new_doc("SD YRP Lot")
	doc.lot_name = f"TA-TEST-{frappe.generate_hash(length=6)}"
	doc.item = item
	doc.flags.ignore_mandatory = True
	doc.flags.ignore_validate = True
	doc.flags.ignore_links = True
	doc.insert()
	if production_order:
		frappe.db.set_value("SD YRP Lot", doc.name, "production_order", production_order)
	return doc.name


def dates(*values):
	return [getdate(value) for value in values]
