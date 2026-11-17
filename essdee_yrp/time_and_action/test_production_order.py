import frappe
from frappe.utils import getdate

from essdee_yrp.time_and_action.create import create_time_and_action
from essdee_yrp.time_and_action.production_order import (
	convert_to_lot_time_and_action,
	get_convertible_lots,
	get_production_order_time_and_action,
)
from essdee_yrp.time_and_action.reports import _allowed_names
from essdee_yrp.time_and_action.steps import log_change
from essdee_yrp.time_and_action.test_create import submitted_production_order
from essdee_yrp.time_and_action.test_rules import DEPENDENCIES, STEPS, save_actuals, set_window
from essdee_yrp.time_and_action.testing import (
	TimeAndActionTestCase,
	make_lot,
	make_master,
	use_company_holidays,
)
from essdee_yrp.time_and_action.update import find_time_and_action, revise_dates
from essdee_yrp.time_and_action.web import get_open_time_and_actions

TIME_AND_ACTION = "SD YRP Time and Action"
LOT = "SD YRP Lot"
PRODUCTION_ORDER = "YRP Production Order"
START = "2026-11-02"
DATE_FIELDS = ("planned_start_date", "date", "rescheduled_date", "actual_date", "reason", "work_station")


def row_values(name):
	doc = frappe.get_doc(TIME_AND_ACTION, name)
	return [(row.action, *(str(row.get(field) or "") for field in DATE_FIELDS)) for row in doc.details]


class TestProductionOrderTimeAndAction(TimeAndActionTestCase):
	def setUp(self):
		use_company_holidays([], "2025-01-01", "2028-12-31")
		set_window(3650, 3650)
		self.master = make_master(STEPS, DEPENDENCIES)
		self.order = submitted_production_order()
		self.lots = [make_lot(production_order=self.order) for _index in range(3)]

	def create_order_time_and_action(self):
		return create_time_and_action(PRODUCTION_ORDER, self.order, self.master.name, START)

	def test_po_create_builds_rows_against_the_order(self):
		doc = frappe.get_doc(TIME_AND_ACTION, self.create_order_time_and_action())
		self.assertEqual(
			(doc.against, doc.against_id, doc.status), (PRODUCTION_ORDER, self.order, "In Progress")
		)
		self.assertEqual([row.action for row in doc.details], [action for action, _lead in STEPS])

	def test_po_create_takes_the_order_item_without_production_detail(self):
		frappe.db.set_value(PRODUCTION_ORDER, self.order, "production_detail", None)
		doc = frappe.get_doc(TIME_AND_ACTION, self.create_order_time_and_action())
		item = frappe.db.get_value(PRODUCTION_ORDER, self.order, "item")
		self.assertTrue(item)
		self.assertEqual(doc.item, item)

	def test_lot_create_blocked_while_po_has_ta(self):
		self.create_order_time_and_action()
		with self.assertRaisesRegex(frappe.ValidationError, "Convert to Lot T&A"):
			create_time_and_action(LOT, self.lots[0], self.master.name, START)

	def test_po_create_blocked_when_a_lot_has_ta(self):
		create_time_and_action(LOT, self.lots[1], self.master.name, START)
		with self.assertRaisesRegex(frappe.ValidationError, self.lots[1]):
			self.create_order_time_and_action()

	def test_linking_lot_with_own_ta_to_po_with_ta_is_refused(self):
		self.create_order_time_and_action()
		lot = make_lot()
		create_time_and_action(LOT, lot, self.master.name, START)
		doc = frappe.get_doc(LOT, lot)
		doc.production_order = self.order
		doc.flags.ignore_mandatory = True
		with self.assertRaisesRegex(frappe.ValidationError, "has Time and Action"):
			doc.save()

	def test_convert_to_one_lot_copies_dates_and_actuals(self):
		source = self.create_order_time_and_action()
		save_actuals(source, {"TA-TEST-YARN": "2026-11-06", "TA-TEST-TRIMS": "2026-11-03"})
		[copy] = convert_to_lot_time_and_action(source, [self.lots[0]])
		doc = frappe.get_doc(TIME_AND_ACTION, copy)
		self.assertEqual((doc.against, doc.against_id, doc.copied_from), (LOT, self.lots[0], source))
		self.assertEqual(row_values(copy), row_values(source))
		self.assertEqual(
			[(row.action, row.dependent_action) for row in doc.dependent_details],
			[
				(row.action, row.dependent_action)
				for row in frappe.get_doc(TIME_AND_ACTION, source).dependent_details
			],
		)
		self.assertEqual(
			(doc.master, str(doc.start_date), doc.status), (self.master.name, START, "In Progress")
		)
		self.assertEqual(
			getdate(doc.end_date), getdate(frappe.db.get_value(TIME_AND_ACTION, source, "end_date"))
		)

	def test_convert_to_two_lots_freezes_po_and_lots_continue_independently(self):
		source = self.create_order_time_and_action()
		save_actuals(source, {"TA-TEST-YARN": "2026-11-04"})
		first, second = convert_to_lot_time_and_action(source, self.lots[:2])
		self.assertEqual(frappe.db.get_value(TIME_AND_ACTION, source, "status"), "Frozen")
		save_actuals(first, {"TA-TEST-KNIT": "2026-11-12"})
		self.assertEqual(frappe.db.get_value(TIME_AND_ACTION, second, "status"), "In Progress")
		knit = {name: frappe.get_doc(TIME_AND_ACTION, name).details[2] for name in (first, second, source)}
		self.assertEqual(str(knit[first].actual_date), "2026-11-12")
		self.assertIsNone(knit[second].actual_date)
		self.assertIsNone(knit[source].actual_date)

	def test_frozen_po_ta_is_read_only(self):
		source = self.create_order_time_and_action()
		convert_to_lot_time_and_action(source, [self.lots[0]])
		with self.assertRaisesRegex(frappe.ValidationError, "Frozen"):
			save_actuals(source, {"TA-TEST-YARN": "2026-11-04"})

	def test_convert_logs_comments_on_both(self):
		source = self.create_order_time_and_action()
		[copy] = convert_to_lot_time_and_action(source, [self.lots[0]])
		for name, text in ((source, copy), (copy, source)):
			comments = frappe.get_all(
				"Comment",
				filters={
					"reference_doctype": TIME_AND_ACTION,
					"reference_name": name,
					"comment_type": "Info",
				},
				pluck="content",
			)
			self.assertTrue(any(text in comment for comment in comments), comments)

	def test_convert_copies_revision_history_and_step_changes(self):
		frappe.db.set_single_value("SD YRP T and A Settings", "revised_date_approver_role", "System Manager")
		frappe.db.set_single_value("SD YRP T and A Settings", "revising_days_limit", 5)
		source = self.create_order_time_and_action()
		revise_dates(source, "buyer moved")
		doc = frappe.get_doc(TIME_AND_ACTION, source)
		log_change(
			doc, "Edit Dependencies", "TA-TEST-CUT", ["TA-TEST-KNIT"], ["TA-TEST-KNIT", "TA-TEST-TRIMS"]
		)
		doc.save()
		[copy] = convert_to_lot_time_and_action(source, [self.lots[0]])
		doc = frappe.get_doc(TIME_AND_ACTION, copy)
		self.assertEqual(doc.revised, 1)
		self.assertEqual(len(doc.time_and_action_revised_dates), len(STEPS))
		self.assertEqual(doc.time_and_action_revised_dates[0].reason, "buyer moved")
		self.assertEqual([row.change_type for row in doc.step_changes], ["Edit Dependencies"])

	def test_convert_refuses_lot_not_linked_to_the_order(self):
		source = self.create_order_time_and_action()
		with self.assertRaisesRegex(frappe.ValidationError, "not linked"):
			convert_to_lot_time_and_action(source, [make_lot()])

	def test_convert_refuses_already_converted_lot(self):
		source = self.create_order_time_and_action()
		convert_to_lot_time_and_action(source, [self.lots[0]])
		with self.assertRaisesRegex(frappe.ValidationError, "already has"):
			convert_to_lot_time_and_action(source, [self.lots[0]])

	def test_convert_is_all_or_nothing(self):
		source = self.create_order_time_and_action()
		with self.assertRaises(frappe.ValidationError):
			convert_to_lot_time_and_action(source, [self.lots[0], make_lot()])
		self.assertIsNone(frappe.db.get_value(TIME_AND_ACTION, {"against": LOT, "against_id": self.lots[0]}))
		self.assertEqual(frappe.db.get_value(TIME_AND_ACTION, source, "status"), "In Progress")

	def test_convert_needs_at_least_one_lot(self):
		source = self.create_order_time_and_action()
		with self.assertRaisesRegex(frappe.ValidationError, "Select at least one Lot"):
			convert_to_lot_time_and_action(source, [])

	def test_convert_only_from_a_production_order_ta(self):
		lot_time_and_action = create_time_and_action(LOT, make_lot(), self.master.name, START)
		with self.assertRaisesRegex(frappe.ValidationError, "Production Order"):
			convert_to_lot_time_and_action(lot_time_and_action, [self.lots[0]])

	def test_convert_from_frozen_for_newly_linked_lot(self):
		source = self.create_order_time_and_action()
		convert_to_lot_time_and_action(source, [self.lots[0]])
		later = make_lot(production_order=self.order)
		with self.assertRaisesRegex(frappe.ValidationError, "Convert to Lot T&A"):
			create_time_and_action(LOT, later, self.master.name, START)
		self.assertIn(later, [row["name"] for row in get_convertible_lots(source)])
		[copy] = convert_to_lot_time_and_action(source, [later])
		self.assertEqual(row_values(copy), row_values(source))

	def test_convertible_lots_are_linked_lots_without_ta(self):
		source = self.create_order_time_and_action()
		convert_to_lot_time_and_action(source, [self.lots[0]])
		names = [row["name"] for row in get_convertible_lots(source)]
		self.assertNotIn(self.lots[0], names)
		self.assertTrue(set(self.lots[1:]) <= set(names))

	def test_convert_accepts_lots_as_json_from_desk(self):
		source = self.create_order_time_and_action()
		created = frappe.call(
			"essdee_yrp.time_and_action.production_order.convert_to_lot_time_and_action",
			time_and_action=source,
			lots=frappe.as_json(self.lots[:2]),
		)
		self.assertEqual(
			[frappe.db.get_value(TIME_AND_ACTION, name, "against_id") for name in created], self.lots[:2]
		)

	def test_frozen_po_ta_is_left_out_of_update_list_and_reports(self):
		source = self.create_order_time_and_action()
		[copy] = convert_to_lot_time_and_action(source, [self.lots[0]])
		self.assertNotIn(source, [row.name for row in get_open_time_and_actions()])
		self.assertIn(copy, [row.name for row in get_open_time_and_actions()])
		self.assertIsNone(find_time_and_action(PRODUCTION_ORDER, self.order))
		self.assertNotIn(source, _allowed_names())

	def test_order_context_for_desk_and_web(self):
		context = get_production_order_time_and_action(self.order)
		self.assertEqual((context["time_and_action"], context["can_create"]), (None, True))
		source = self.create_order_time_and_action()
		context = get_production_order_time_and_action(self.order)
		self.assertEqual((context["time_and_action"], context["status"]), (source, "In Progress"))
		self.assertFalse(context["can_create"])
		self.assertTrue(context["can_convert"])
		[copy] = convert_to_lot_time_and_action(source, [self.lots[0]])
		context = get_production_order_time_and_action(self.order)
		self.assertEqual(context["status"], "Frozen")
		self.assertEqual([row["name"] for row in context["copies"]], [copy])
