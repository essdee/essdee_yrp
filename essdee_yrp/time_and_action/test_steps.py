import json

import frappe
from frappe.utils import getdate

from essdee_yrp.time_and_action.create import create_time_and_action
from essdee_yrp.time_and_action.steps import preview_update_actions, update_actions
from essdee_yrp.time_and_action.test_rules import DEPENDENCIES, STEPS, save_actuals, set_window
from essdee_yrp.time_and_action.test_update import make_user
from essdee_yrp.time_and_action.testing import (
	TimeAndActionTestCase,
	make_action,
	make_lot,
	make_master,
	use_company_holidays,
)
from essdee_yrp.time_and_action.update import complete_time_and_action, get_update_data

TIME_AND_ACTION = "SD YRP Time and Action"
SETTINGS = "SD YRP T and A Settings"
PRINT = "TA-TEST-PRINT"


def add(
	action=PRINT,
	after="TA-TEST-KNIT",
	depends_on=("TA-TEST-KNIT",),
	required_by=("TA-TEST-CUT",),
	lead_time=2,
):
	return {
		"action": action,
		"lead_time": lead_time,
		"after_action": after,
		"depends_on": list(depends_on),
		"required_by": list(required_by),
	}


class StepTestCase(TimeAndActionTestCase):
	"""Start 02-11-2026, no holidays: YARN 04-11, TRIMS 05-11, KNIT 07-11, CUT 08-11 (delivery)."""

	def setUp(self):
		use_company_holidays([], "2025-01-01", "2028-12-31")
		set_window(3650, 3650)
		make_action(PRINT, 2)
		master = make_master(STEPS, DEPENDENCIES)
		self.name = create_time_and_action("SD YRP Lot", make_lot(), master.name, "2026-11-02")

	def doc(self):
		return frappe.get_doc(TIME_AND_ACTION, self.name)

	def rows(self):
		return {row.action: row for row in self.doc().details}

	def dependencies(self, action):
		return sorted(row.dependent_action for row in self.doc().dependent_details if row.action == action)


class TestUpdateActions(StepTestCase):
	def test_add_with_depends_on_and_required_by_pushes_dates_out(self):
		update_actions(self.name, add=[add()])
		doc = self.doc()
		self.assertEqual([row.action for row in doc.details][3], PRINT)
		rows = self.rows()
		self.assertEqual(getdate(rows[PRINT].rescheduled_date), getdate("2026-11-09"))
		self.assertEqual(getdate(rows[PRINT].date), getdate("2026-11-09"))
		self.assertEqual(getdate(rows[PRINT].planned_start_date), getdate("2026-11-09"))
		self.assertEqual(getdate(rows["TA-TEST-CUT"].rescheduled_date), getdate("2026-11-10"))
		self.assertEqual(getdate(rows["TA-TEST-CUT"].date), getdate("2026-11-08"))
		self.assertEqual(getdate(doc.end_date), getdate("2026-11-10"))
		self.assertEqual(self.dependencies(PRINT), ["TA-TEST-KNIT"])
		self.assertIn(PRINT, self.dependencies("TA-TEST-CUT"))

	def test_preview_reports_delivery_impact_without_saving(self):
		result = preview_update_actions(self.name, add=[add()])
		self.assertEqual(getdate(result["delivery_date_before"]), getdate("2026-11-08"))
		self.assertEqual(getdate(result["delivery_date_after"]), getdate("2026-11-10"))
		self.assertEqual(result["delivery_days_moved"], 2)
		self.assertIn(PRINT, [row["action"] for row in result["rows"]])
		self.assertNotIn(PRINT, self.rows())

	def test_remove_pulls_dates_in_and_unlinks_dependents(self):
		result = preview_update_actions(self.name, remove=["TA-TEST-KNIT"])
		self.assertEqual(result["delivery_days_moved"], -2)
		update_actions(self.name, remove=["TA-TEST-KNIT"])
		rows = self.rows()
		self.assertNotIn("TA-TEST-KNIT", rows)
		self.assertEqual(self.dependencies("TA-TEST-CUT"), ["TA-TEST-TRIMS"])
		self.assertEqual(getdate(rows["TA-TEST-CUT"].rescheduled_date), getdate("2026-11-06"))
		self.assertEqual(getdate(self.doc().end_date), getdate("2026-11-06"))

	def test_remove_dated_step_is_refused(self):
		save_actuals(self.name, {"TA-TEST-YARN": "2026-11-04"})
		with self.assertRaisesRegex(frappe.ValidationError, "actual date"):
			update_actions(self.name, remove=["TA-TEST-YARN"])

	def test_add_between_completed_actions_is_refused(self):
		save_actuals(self.name, {"TA-TEST-YARN": "2026-11-04", "TA-TEST-TRIMS": "2026-11-05"})
		item = add(after="TA-TEST-YARN", depends_on=["TA-TEST-YARN"], required_by=[])
		with self.assertRaisesRegex(
			frappe.ValidationError, "after the last completed action \\(TA-TEST-TRIMS\\)"
		):
			update_actions(self.name, add=[item])
		update_actions(self.name, add=[{**item, "after_action": "TA-TEST-TRIMS"}])
		self.assertEqual([row.action for row in self.doc().details][2], PRINT)

	def test_required_by_dated_step_is_refused(self):
		save_actuals(self.name, {"TA-TEST-YARN": "2026-11-04"})
		with self.assertRaisesRegex(frappe.ValidationError, "TA-TEST-YARN"):
			update_actions(
				self.name, add=[add(after="TA-TEST-YARN", depends_on=[], required_by=["TA-TEST-YARN"])]
			)

	def test_cycle_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "TA-TEST-CUT"):
			update_actions(
				self.name,
				add=[add(after="TA-TEST-KNIT", depends_on=["TA-TEST-CUT"], required_by=["TA-TEST-KNIT"])],
			)
		with self.assertRaisesRegex(frappe.ValidationError, "TA-TEST-KNIT"):
			update_actions(
				self.name, add=[add(after="TA-TEST-YARN", depends_on=["TA-TEST-KNIT"], required_by=[])]
			)

	def test_duplicate_action_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "already"):
			update_actions(self.name, add=[add(action="TA-TEST-KNIT")])

	def test_lead_time_below_one_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Lead Time"):
			update_actions(self.name, add=[add(lead_time=0)])

	def test_completed_ta_is_locked(self):
		save_actuals(
			self.name,
			{
				"TA-TEST-YARN": "2026-11-04",
				"TA-TEST-TRIMS": "2026-11-05",
				"TA-TEST-KNIT": "2026-11-07",
				"TA-TEST-CUT": "2026-11-08",
			},
		)
		complete_time_and_action(self.name)
		self.assertFalse(get_update_data(self.name)["can_edit_steps"])
		with self.assertRaisesRegex(frappe.ValidationError, "Completed"):
			update_actions(
				self.name, add=[add(after="TA-TEST-CUT", depends_on=["TA-TEST-CUT"], required_by=[])]
			)

	def test_step_editing_requires_role(self):
		frappe.db.set_single_value(SETTINGS, "step_editor_role", "T & A Manager")
		frappe.set_user(make_user("T & A User"))
		self.assertFalse(get_update_data(self.name)["can_edit_steps"])
		with self.assertRaises(frappe.PermissionError):
			update_actions(self.name, remove=["TA-TEST-TRIMS"])
		frappe.set_user(make_user("T & A User", "T & A Manager"))
		self.assertTrue(get_update_data(self.name)["can_edit_steps"])
		update_actions(self.name, remove=["TA-TEST-TRIMS"])
		self.assertNotIn("TA-TEST-TRIMS", self.rows())

	def test_batch_applies_adds_and_removes_together(self):
		update_actions(self.name, add=[add(required_by=["TA-TEST-CUT"])], remove=["TA-TEST-TRIMS"])
		self.assertEqual(
			[row.action for row in self.doc().details], ["TA-TEST-YARN", "TA-TEST-KNIT", PRINT, "TA-TEST-CUT"]
		)
		self.assertEqual(self.dependencies("TA-TEST-CUT"), ["TA-TEST-KNIT", PRINT])

	def test_batch_is_atomic(self):
		with self.assertRaisesRegex(frappe.ValidationError, "already"):
			update_actions(self.name, add=[add(action="TA-TEST-KNIT")], remove=["TA-TEST-TRIMS"])
		self.assertIn("TA-TEST-TRIMS", self.rows())

	def test_changes_are_logged(self):
		update_actions(self.name, add=[add()], remove=["TA-TEST-TRIMS"])
		changes = {row.change_type: row for row in self.doc().step_changes}
		self.assertEqual(changes["Add Step"].action, PRINT)
		self.assertEqual(changes["Add Step"].user, "Administrator")
		self.assertEqual(json.loads(changes["Add Step"].after)["required_by"], ["TA-TEST-CUT"])
		self.assertEqual(changes["Remove Step"].action, "TA-TEST-TRIMS")
		self.assertIn("TA-TEST-CUT", json.loads(changes["Remove Step"].before)["required_by"])
		comment = frappe.get_all(
			"Comment", filters={"reference_name": self.name, "comment_type": "Info"}, pluck="content"
		)
		self.assertTrue(
			any(f"Added {PRINT} (2 days) after TA-TEST-KNIT; before TA-TEST-CUT" in text for text in comment)
		)
		self.assertTrue(any("Removed TA-TEST-TRIMS" in text for text in comment))

	def test_frappe_call_with_string_args(self):
		result = frappe.call(
			"essdee_yrp.time_and_action.steps.preview_update_actions",
			time_and_action=self.name,
			add=json.dumps([add()]),
			remove=json.dumps([]),
		)
		self.assertEqual(result["delivery_days_moved"], 2)
		frappe.call(
			"essdee_yrp.time_and_action.steps.update_actions",
			time_and_action=self.name,
			add=json.dumps([add()]),
			remove="[]",
		)
		self.assertIn(PRINT, self.rows())


def edit(action, *depends_on):
	return {"action": action, "depends_on": list(depends_on)}


class TestEditDependencies(StepTestCase):
	"""Edit Dependencies (requirement 31) runs in the same Update Action batch."""

	def test_adding_a_dependency_pushes_dates_out(self):
		update_actions(self.name, edit=[edit("TA-TEST-KNIT", "TA-TEST-YARN", "TA-TEST-TRIMS")])
		rows = self.rows()
		self.assertEqual(self.dependencies("TA-TEST-KNIT"), ["TA-TEST-TRIMS", "TA-TEST-YARN"])
		self.assertEqual(getdate(rows["TA-TEST-KNIT"].rescheduled_date), getdate("2026-11-08"))
		self.assertEqual(getdate(self.doc().end_date), getdate("2026-11-09"))

	def test_dropping_a_dependency_pulls_dates_in(self):
		result = preview_update_actions(self.name, edit=[edit("TA-TEST-CUT", "TA-TEST-TRIMS")])
		self.assertEqual(result["delivery_days_moved"], -2)
		self.assertEqual(self.dependencies("TA-TEST-CUT"), ["TA-TEST-KNIT", "TA-TEST-TRIMS"])
		update_actions(self.name, edit=[edit("TA-TEST-CUT", "TA-TEST-TRIMS")])
		self.assertEqual(self.dependencies("TA-TEST-CUT"), ["TA-TEST-TRIMS"])
		self.assertEqual(getdate(self.doc().end_date), getdate("2026-11-06"))

	def test_edit_is_logged(self):
		update_actions(self.name, edit=[edit("TA-TEST-CUT", "TA-TEST-KNIT", "TA-TEST-YARN")])
		change = self.doc().step_changes[0]
		self.assertEqual(change.change_type, "Edit Dependencies")
		self.assertEqual(change.action, "TA-TEST-CUT")
		self.assertEqual(json.loads(change.before)["depends_on"], ["TA-TEST-KNIT", "TA-TEST-TRIMS"])
		self.assertEqual(json.loads(change.after)["depends_on"], ["TA-TEST-KNIT", "TA-TEST-YARN"])
		comment = frappe.get_all(
			"Comment", filters={"reference_name": self.name, "comment_type": "Info"}, pluck="content"
		)
		expected = (
			"Changed TA-TEST-CUT dependencies: TA-TEST-KNIT, TA-TEST-TRIMS → TA-TEST-KNIT, TA-TEST-YARN."
		)
		self.assertTrue(any(expected in text for text in comment))

	def test_cycle_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "cycle"):
			update_actions(self.name, edit=[edit("TA-TEST-YARN", "TA-TEST-CUT")])

	def test_forward_dependency_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "above it, not TA-TEST-KNIT"):
			update_actions(self.name, edit=[edit("TA-TEST-TRIMS", "TA-TEST-KNIT")])

	def test_self_dependency_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "itself"):
			update_actions(self.name, edit=[edit("TA-TEST-KNIT", "TA-TEST-KNIT")])

	def test_dependency_outside_the_ta_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "not part of this Time and Action"):
			update_actions(self.name, edit=[edit("TA-TEST-KNIT", PRINT)])

	def test_editing_a_dated_action_is_refused(self):
		save_actuals(self.name, {"TA-TEST-YARN": "2026-11-04", "TA-TEST-TRIMS": "2026-11-05"})
		with self.assertRaisesRegex(frappe.ValidationError, "locked"):
			update_actions(self.name, edit=[edit("TA-TEST-TRIMS", "TA-TEST-YARN")])

	def test_edit_can_use_an_action_added_in_the_same_batch(self):
		item = add(required_by=[])
		update_actions(self.name, add=[item], edit=[edit("TA-TEST-CUT", "TA-TEST-TRIMS", PRINT)])
		self.assertEqual(self.dependencies("TA-TEST-CUT"), [PRINT, "TA-TEST-TRIMS"])

	def test_frappe_call_with_string_edit(self):
		args = {"time_and_action": self.name, "edit": json.dumps([edit("TA-TEST-CUT", "TA-TEST-TRIMS")])}
		result = frappe.call("essdee_yrp.time_and_action.steps.preview_update_actions", **args)
		self.assertEqual(result["delivery_days_moved"], -2)
		frappe.call("essdee_yrp.time_and_action.steps.update_actions", **args)
		self.assertEqual(self.dependencies("TA-TEST-CUT"), ["TA-TEST-TRIMS"])
