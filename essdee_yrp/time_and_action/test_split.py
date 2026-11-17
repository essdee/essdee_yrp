import frappe

from essdee_yrp.time_and_action.create import create_time_and_action
from essdee_yrp.time_and_action.split import get_split_lots, split_time_and_action
from essdee_yrp.time_and_action.test_create import submitted_production_order
from essdee_yrp.time_and_action.test_production_order import row_values
from essdee_yrp.time_and_action.test_rules import DEPENDENCIES, STEPS, save_actuals, set_window
from essdee_yrp.time_and_action.testing import (
	TimeAndActionTestCase,
	make_lot,
	make_master,
	use_company_holidays,
)
from essdee_yrp.time_and_action.update import complete_time_and_action, get_update_data

TIME_AND_ACTION = "SD YRP Time and Action"
LOT = "SD YRP Lot"
PRODUCTION_ORDER = "YRP Production Order"
START = "2026-11-02"
ALL_ACTUALS = {
	"TA-TEST-YARN": "2026-11-04",
	"TA-TEST-TRIMS": "2026-11-03",
	"TA-TEST-KNIT": "2026-11-09",
	"TA-TEST-CUT": "2026-11-10",
}


def status(name):
	return frappe.db.get_value(TIME_AND_ACTION, name, "status")


def lot_time_and_action(lot):
	return frappe.db.get_value(TIME_AND_ACTION, {"against": LOT, "against_id": lot})


def info_comments(name):
	return frappe.get_all(
		"Comment",
		filters={"reference_doctype": TIME_AND_ACTION, "reference_name": name, "comment_type": "Info"},
		pluck="content",
	)


class TestSplitTimeAndAction(TimeAndActionTestCase):
	def setUp(self):
		use_company_holidays([], "2025-01-01", "2028-12-31")
		set_window(3650, 3650)
		self.master = make_master(STEPS, DEPENDENCIES)
		self.lot = make_lot()
		self.source = create_time_and_action(LOT, self.lot, self.master.name, START)
		self.targets = [make_lot(), make_lot()]

	def test_split_copies_all_rows_and_actuals(self):
		save_actuals(self.source, {"TA-TEST-YARN": "2026-11-06", "TA-TEST-TRIMS": "2026-11-03"})
		[copy] = split_time_and_action(self.source, [self.targets[0]])
		doc = frappe.get_doc(TIME_AND_ACTION, copy)
		self.assertEqual((doc.against, doc.against_id, doc.copied_from), (LOT, self.targets[0], self.source))
		self.assertEqual(row_values(copy), row_values(self.source))
		self.assertEqual(
			[(row.action, row.dependent_action) for row in doc.dependent_details],
			[
				(action, dependency)
				for action, depends_on in DEPENDENCIES.items()
				for dependency in depends_on
			],
		)
		self.assertEqual(
			(doc.master, str(doc.start_date), doc.status), (self.master.name, START, "In Progress")
		)
		self.assertEqual(status(self.source), "In Progress")

	def test_split_to_two_lots_and_targets_update_independently(self):
		save_actuals(self.source, {"TA-TEST-YARN": "2026-11-04"})
		first, second = split_time_and_action(self.source, self.targets)
		self.assertEqual([lot_time_and_action(lot) for lot in self.targets], [first, second])
		save_actuals(first, {"TA-TEST-KNIT": "2026-11-12"})
		save_actuals(self.source, {"TA-TEST-TRIMS": "2026-11-05"})
		rows = {name: frappe.get_doc(TIME_AND_ACTION, name).details for name in (first, second, self.source)}
		self.assertEqual(str(rows[first][2].actual_date), "2026-11-12")
		self.assertIsNone(rows[second][2].actual_date)
		self.assertIsNone(rows[self.source][2].actual_date)
		self.assertEqual(str(rows[self.source][1].actual_date), "2026-11-05")
		self.assertIsNone(rows[first][1].actual_date)
		self.assertEqual(str(rows[second][0].actual_date), "2026-11-04")

	def test_split_logs_comments_on_source_and_copies(self):
		created = split_time_and_action(self.source, self.targets)
		source_comments = info_comments(self.source)
		for name, lot in zip(created, self.targets, strict=True):
			self.assertTrue(any(name in text and lot in text for text in source_comments), source_comments)
			self.assertTrue(any(self.source in text for text in info_comments(name)))

	def test_split_refuses_lot_with_ta_or_po_ta(self):
		create_time_and_action(LOT, self.targets[0], self.master.name, START)
		with self.assertRaisesRegex(frappe.ValidationError, "already has"):
			split_time_and_action(self.source, [self.targets[0]])
		order = submitted_production_order()
		blocked = make_lot(production_order=order)
		create_time_and_action(PRODUCTION_ORDER, order, self.master.name, START)
		with self.assertRaisesRegex(frappe.ValidationError, "Convert to Lot T&A"):
			split_time_and_action(self.source, [blocked])

	def test_split_refuses_own_lot_and_duplicates(self):
		with self.assertRaisesRegex(frappe.ValidationError, "already has"):
			split_time_and_action(self.source, [self.lot])
		with self.assertRaisesRegex(frappe.ValidationError, "only once"):
			split_time_and_action(self.source, [self.targets[0], self.targets[0]])

	def test_split_is_all_or_nothing(self):
		create_time_and_action(LOT, self.targets[1], self.master.name, START)
		with self.assertRaises(frappe.ValidationError):
			split_time_and_action(self.source, self.targets)
		self.assertIsNone(lot_time_and_action(self.targets[0]))

	def test_split_needs_at_least_one_lot(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Select at least one Lot"):
			split_time_and_action(self.source, [])

	def test_split_from_po_ta_is_refused(self):
		order = submitted_production_order()
		source = create_time_and_action(PRODUCTION_ORDER, order, self.master.name, START)
		with self.assertRaisesRegex(frappe.ValidationError, "Lot's Time and Action"):
			split_time_and_action(source, [self.targets[0]])

	def test_split_refused_unless_in_progress(self):
		save_actuals(self.source, ALL_ACTUALS)
		complete_time_and_action(self.source)
		with self.assertRaisesRegex(frappe.ValidationError, "Completed"):
			split_time_and_action(self.source, [self.targets[0]])
		self.assertIsNone(lot_time_and_action(self.targets[0]))

	def test_split_accepts_lots_as_json_from_desk(self):
		created = frappe.call(
			"essdee_yrp.time_and_action.split.split_time_and_action",
			time_and_action=self.source,
			lots=frappe.as_json(self.targets),
		)
		self.assertEqual(
			[frappe.db.get_value(TIME_AND_ACTION, name, "against_id") for name in created], self.targets
		)

	def test_split_accepts_one_lot_as_plain_string(self):
		[copy] = frappe.call(
			"essdee_yrp.time_and_action.split.split_time_and_action",
			time_and_action=self.source,
			lots=self.targets[0],
		)
		self.assertEqual(frappe.db.get_value(TIME_AND_ACTION, copy, "against_id"), self.targets[0])

	def test_split_lots_are_lots_without_ta_or_po_ta(self):
		create_time_and_action(LOT, self.targets[1], self.master.name, START)
		order = submitted_production_order()
		create_time_and_action(PRODUCTION_ORDER, order, self.master.name, START)
		blocked = make_lot(production_order=order)
		names = {row["name"] for row in get_split_lots(self.source, "TA-TEST-")}
		self.assertIn(self.targets[0], names)
		self.assertFalse({self.lot, self.targets[1], blocked} & names)
		self.assertEqual(
			[row["name"] for row in get_split_lots(self.source, self.targets[0])], [self.targets[0]]
		)

	def test_update_data_offers_split_only_for_in_progress_lot_ta(self):
		self.assertTrue(get_update_data(self.source)["can_split"])
		order = create_time_and_action(
			PRODUCTION_ORDER, submitted_production_order(), self.master.name, START
		)
		self.assertFalse(get_update_data(order)["can_split"])
		save_actuals(self.source, ALL_ACTUALS)
		complete_time_and_action(self.source)
		self.assertFalse(get_update_data(self.source)["can_split"])
