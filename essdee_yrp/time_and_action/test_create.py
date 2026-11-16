import frappe
from frappe.utils import getdate

from essdee_yrp.time_and_action.create import create_time_and_action, get_schedule_preview
from essdee_yrp.time_and_action.holidays import get_company_holidays
from essdee_yrp.time_and_action.schedule import ScheduleRow, build_schedule
from essdee_yrp.time_and_action.testing import (
	TimeAndActionTestCase,
	make_action,
	make_lot,
	make_master,
	use_company_holidays,
)

STEPS = [("TA-TEST-YARN", 2), ("TA-TEST-KNIT", 3), ("TA-TEST-TRIMS", 1), ("TA-TEST-CUT", 1)]
DEPENDENCIES = {"TA-TEST-KNIT": ["TA-TEST-YARN"], "TA-TEST-CUT": ["TA-TEST-KNIT", "TA-TEST-TRIMS"]}
START = "2026-11-02"


def submitted_production_order():
	name = frappe.db.get_value("YRP Production Order", {"docstatus": 1}, "name")
	if not name:
		raise AssertionError("erp-migration-test needs a submitted YRP Production Order")
	return name


def make_work_stations(action):
	"""A default and a second Work Station for a capacity-planned `action`."""
	frappe.db.set_value("SD YRP Action", action, "capacity_planning", 1)
	frappe.db.set_value("YRP Work Station", {"default": 1}, "default", 0)
	names = []
	for is_default in (1, 0):
		doc = frappe.get_doc(
			{
				"doctype": "YRP Work Station",
				"workstation_name": f"TA-TEST-{frappe.generate_hash(length=6)}",
				"action": action,
				"default": is_default,
			}
		).insert()
		names.append(doc.name)
	return names


class TestCreateTimeAndAction(TimeAndActionTestCase):
	def setUp(self):
		use_company_holidays(["2026-11-08", "2026-11-15"])
		self.master = make_master(STEPS, DEPENDENCIES)

	def test_create_lot_ta_builds_rows_from_master(self):
		lot = make_lot()
		doc = frappe.get_doc(
			"SD YRP Time and Action", create_time_and_action("SD YRP Lot", lot, self.master.name, START)
		)
		expected = build_schedule(
			[ScheduleRow(action, lead) for action, lead in STEPS], DEPENDENCIES, START, get_company_holidays()
		)
		self.assertEqual([row.action for row in doc.details], [action for action, _lead in STEPS])
		self.assertEqual({row.action: getdate(row.date) for row in doc.details}, expected)
		self.assertEqual({row.action: getdate(row.rescheduled_date) for row in doc.details}, expected)
		self.assertEqual(getdate(doc.end_date), expected["TA-TEST-CUT"])
		self.assertEqual(len(doc.dependent_details), 3)
		self.assertTrue(doc.name.startswith("TA-"))

	def test_preview_matches_created_rows(self):
		preview = get_schedule_preview(self.master.name, START)
		self.assertEqual([row["action"] for row in preview], [action for action, _lead in STEPS])
		self.assertEqual(str(preview[-1]["date"]), "2026-11-10")

	def test_preview_returns_default_work_station(self):
		default, _other = make_work_stations("TA-TEST-CUT")
		preview = {
			row["action"]: row["work_station"] for row in get_schedule_preview(self.master.name, START)
		}
		self.assertEqual(preview["TA-TEST-CUT"], default)
		self.assertIsNone(preview["TA-TEST-YARN"])

	def test_create_honours_chosen_work_station(self):
		default, other = make_work_stations("TA-TEST-CUT")
		name = create_time_and_action(
			"SD YRP Lot", make_lot(), self.master.name, START, {"TA-TEST-CUT": other, "TA-TEST-YARN": None}
		)
		stations = {
			row.action: row.work_station for row in frappe.get_doc("SD YRP Time and Action", name).details
		}
		self.assertEqual(stations["TA-TEST-CUT"], other)
		self.assertIsNone(stations["TA-TEST-YARN"])
		default_name = create_time_and_action("SD YRP Lot", make_lot(), self.master.name, START)
		self.assertEqual(
			frappe.get_doc("SD YRP Time and Action", default_name).details[3].work_station, default
		)

	def test_create_accepts_work_stations_as_json_from_desk(self):
		_default, other = make_work_stations("TA-TEST-CUT")
		name = frappe.call(
			"essdee_yrp.time_and_action.create.create_time_and_action",
			against="SD YRP Lot",
			against_id=make_lot(),
			master=self.master.name,
			start_date=START,
			work_stations=frappe.as_json({"TA-TEST-CUT": other}),
		)
		self.assertEqual(frappe.get_doc("SD YRP Time and Action", name).details[3].work_station, other)

	def test_second_ta_for_same_lot_is_refused(self):
		lot = make_lot()
		create_time_and_action("SD YRP Lot", lot, self.master.name, START)
		with self.assertRaisesRegex(frappe.ValidationError, "already has"):
			create_time_and_action("SD YRP Lot", lot, self.master.name, START)

	def test_lot_of_po_with_ta_cannot_create(self):
		order = submitted_production_order()
		create_time_and_action("YRP Production Order", order, self.master.name, START)
		lot = make_lot(production_order=order)
		with self.assertRaisesRegex(frappe.ValidationError, "Convert to Lot T&A"):
			create_time_and_action("SD YRP Lot", lot, self.master.name, START)

	def test_po_with_lot_ta_cannot_create(self):
		order = submitted_production_order()
		lot = make_lot(production_order=order)
		create_time_and_action("SD YRP Lot", lot, self.master.name, START)
		with self.assertRaisesRegex(frappe.ValidationError, lot):
			create_time_and_action("YRP Production Order", order, self.master.name, START)

	def test_against_must_be_lot_or_production_order(self):
		with self.assertRaises(frappe.ValidationError):
			create_time_and_action("Item", frappe.db.get_value("Item", {}), self.master.name, START)

	def test_editing_master_does_not_change_existing_ta(self):
		lot = make_lot()
		name = create_time_and_action("SD YRP Lot", lot, self.master.name, START)
		self.master.details[0].lead_time = 9
		self.master.save()
		doc = frappe.get_doc("SD YRP Time and Action", name)
		doc.save()
		self.assertEqual(doc.details[0].lead_time, 2)
		self.assertEqual(str(doc.details[0].rescheduled_date), "2026-11-04")

	def test_master_dependency_must_be_earlier_row(self):
		with self.assertRaisesRegex(frappe.ValidationError, "earlier"):
			make_master([("TA-TEST-A", 1), ("TA-TEST-B", 1)], {"TA-TEST-A": ["TA-TEST-B"]})

	def test_master_self_dependency_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "itself"):
			make_master([("TA-TEST-A", 1)], {"TA-TEST-A": ["TA-TEST-A"]})

	def test_master_duplicate_action_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "more than once"):
			make_master([("TA-TEST-A", 1), ("TA-TEST-A", 2)], {})

	def test_master_lead_time_zero_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Lead Time"):
			make_master([("TA-TEST-A", 1), ("TA-TEST-B", 0)], {})

	def test_master_without_actions_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "at least one"):
			make_master([], {})

	def test_master_dependency_without_action_is_refused(self):
		master = make_master([("TA-TEST-A", 1), ("TA-TEST-B", 1)], {})
		master.append("action_master_dependent_details", {"action": "TA-TEST-B"})
		with self.assertRaisesRegex(frappe.ValidationError, "Dependent Action"):
			master.save()

	def test_action_lead_time_zero_is_refused(self):
		action = frappe.get_doc("SD YRP Action", make_action("TA-TEST-A"))
		action.lead_time = 0
		with self.assertRaisesRegex(frappe.ValidationError, "Lead Time"):
			action.save()
