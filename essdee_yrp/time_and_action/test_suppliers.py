import json

import frappe

from essdee_yrp.time_and_action.create import LOT, PRODUCTION_ORDER, TIME_AND_ACTION, create_time_and_action
from essdee_yrp.time_and_action.production_order import convert_to_lot_time_and_action
from essdee_yrp.time_and_action.split import split_time_and_action
from essdee_yrp.time_and_action.steps import update_actions
from essdee_yrp.time_and_action.suppliers import (
	get_row_actuals,
	get_supplier_chips,
	set_planned_suppliers,
)
from essdee_yrp.time_and_action.test_create import submitted_production_order
from essdee_yrp.time_and_action.test_production_order import row_values
from essdee_yrp.time_and_action.test_rules import DEPENDENCIES, STEPS, set_window
from essdee_yrp.time_and_action.testing import (
	TimeAndActionTestCase,
	make_lot,
	make_master,
	use_company_holidays,
)
from essdee_yrp.time_and_action.update import get_update_data

START = "2026-11-02"
KNIT, YARN = "TA-TEST-KNIT", "TA-TEST-YARN"
PROCESS = "TA-TEST-PROCESS"
ITEM_GROUP = "TA-TEST-GROUP"


def test_suppliers():
	return frappe.get_all("Supplier", filters={"disabled": 0}, pluck="name", limit=3, order_by="name")


def planned(name):
	doc = frappe.get_doc(TIME_AND_ACTION, name)
	return [(row.action, row.supplier) for row in doc.planned_suppliers]


def insert_work_order(lot, supplier, delivered, received, process=PROCESS, docstatus=1):
	doc = frappe.get_doc(
		{
			"doctype": "YRP Work Order",
			"lot": lot,
			"process_name": process,
			"supplier": supplier,
			"supplier_name": supplier,
			"total_no_of_pieces_delivered": delivered,
			"total_no_of_pieces_received": received,
			"docstatus": docstatus,
		}
	)
	doc.name = f"TA-TEST-WO-{frappe.generate_hash(length=8)}"
	doc.db_insert()
	return doc.name


def insert_purchase_order(supplier, lines, docstatus=1):
	"""`lines`: [(lot, qty, received_qty, item_group, item_code)]."""
	doc = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": supplier,
			"supplier_name": supplier,
			"docstatus": docstatus,
			"items": [
				{
					"lot": lot,
					"qty": qty,
					"received_qty": received,
					"item_group": item_group,
					"item_code": item_code,
				}
				for lot, qty, received, item_group, item_code in lines
			],
		}
	)
	doc.name = f"TA-TEST-PO-{frappe.generate_hash(length=8)}"
	doc.db_insert()
	for row in doc.items:
		row.parent, row.parenttype, row.parentfield, row.docstatus = doc.name, doc.doctype, "items", docstatus
		row.name = frappe.generate_hash(length=10)
		row.db_insert()
	return doc.name


def map_action(action, process=None, item_groups=()):
	doc = frappe.get_doc("SD YRP Action", action)
	doc.process_name = process
	doc.set("purchase_item_groups", [{"item_group": group} for group in item_groups])
	doc.flags.ignore_links = True
	doc.save()


class TestPlannedSuppliers(TimeAndActionTestCase):
	def setUp(self):
		use_company_holidays([], "2025-01-01", "2028-12-31")
		set_window(3650, 3650)
		self.master = make_master(STEPS, DEPENDENCIES)
		self.lot = make_lot()
		self.suppliers = test_suppliers()

	def create(self, planned_suppliers=None):
		return create_time_and_action(
			LOT, self.lot, self.master.name, START, planned_suppliers=json.dumps(planned_suppliers or {})
		)

	def test_planned_suppliers_multi_select_saved_at_create(self):
		name = self.create({KNIT: self.suppliers[:2]})
		self.assertEqual(planned(name), [(KNIT, self.suppliers[0]), (KNIT, self.suppliers[1])])

	def test_set_planned_suppliers_replaces_one_action_with_string_args(self):
		name = self.create({KNIT: self.suppliers[:2], YARN: [self.suppliers[0]]})
		result = set_planned_suppliers(name, KNIT, json.dumps([self.suppliers[2]]))
		self.assertEqual(planned(name), [(YARN, self.suppliers[0]), (KNIT, self.suppliers[2])])
		self.assertEqual(result["modified"], str(frappe.db.get_value(TIME_AND_ACTION, name, "modified")))
		self.assertIn(KNIT, result["chips"])

	def test_duplicate_planned_supplier_is_refused(self):
		name = self.create()
		with self.assertRaises(frappe.ValidationError):
			set_planned_suppliers(name, KNIT, [self.suppliers[0], self.suppliers[0]])

	def test_planned_supplier_for_unknown_action_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.create({"TA-TEST-NOT-A-STEP": [self.suppliers[0]]})

	def test_planned_suppliers_do_not_change_dates(self):
		name = self.create()
		before = row_values(name)
		set_planned_suppliers(name, KNIT, self.suppliers[:2])
		self.assertEqual(row_values(name), before)

	def test_planned_suppliers_locked_on_completed_or_frozen(self):
		name = self.create()
		frappe.db.set_value(TIME_AND_ACTION, name, "status", "Frozen")
		with self.assertRaises(frappe.ValidationError):
			set_planned_suppliers(name, KNIT, [self.suppliers[0]])

	def test_update_data_says_whether_planned_suppliers_can_be_edited(self):
		name = self.create()
		self.assertTrue(get_update_data(name)["can_edit_suppliers"])
		frappe.db.set_value(TIME_AND_ACTION, name, "status", "Completed")
		self.assertFalse(get_update_data(name)["can_edit_suppliers"])

	def test_split_copies_planned_suppliers(self):
		name = self.create({KNIT: self.suppliers[:2]})
		[copy] = split_time_and_action(name, [make_lot()])
		self.assertEqual(planned(copy), planned(name))

	def test_removing_a_step_drops_its_planned_suppliers(self):
		frappe.db.set_single_value("SD YRP T and A Settings", "step_editor_role", "System Manager")
		name = self.create({"TA-TEST-TRIMS": [self.suppliers[0]], KNIT: [self.suppliers[1]]})
		update_actions(name, remove=json.dumps(["TA-TEST-TRIMS"]))
		self.assertEqual(planned(name), [(KNIT, self.suppliers[1])])


class TestConvertCopiesPlannedSuppliers(TimeAndActionTestCase):
	def setUp(self):
		use_company_holidays([], "2025-01-01", "2028-12-31")
		set_window(3650, 3650)
		self.master = make_master(STEPS, DEPENDENCIES)
		self.order = submitted_production_order()
		self.lot = make_lot(production_order=self.order)
		self.suppliers = test_suppliers()

	def test_convert_copies_planned_suppliers(self):
		source = create_time_and_action(
			PRODUCTION_ORDER,
			self.order,
			self.master.name,
			START,
			planned_suppliers={KNIT: self.suppliers[:2]},
		)
		[copy] = convert_to_lot_time_and_action(source, [self.lot])
		self.assertEqual(planned(copy), [(KNIT, self.suppliers[0]), (KNIT, self.suppliers[1])])

	def test_production_order_ta_reads_actuals_of_linked_lots(self):
		map_action(KNIT, PROCESS)
		other_lot = make_lot(production_order=self.order)
		insert_work_order(self.lot, self.suppliers[0], 10, 4)
		insert_work_order(other_lot, self.suppliers[0], 5, 1)
		insert_work_order(make_lot(), self.suppliers[0], 99, 99)
		source = create_time_and_action(PRODUCTION_ORDER, self.order, self.master.name, START)
		[entry] = get_row_actuals(source)[KNIT]
		self.assertEqual((entry["delivered"], entry["received"]), (15, 5))


class TestRowActuals(TimeAndActionTestCase):
	def setUp(self):
		use_company_holidays([], "2025-01-01", "2028-12-31")
		set_window(3650, 3650)
		self.master = make_master(STEPS, DEPENDENCIES)
		self.lot = make_lot()
		self.name = create_time_and_action(LOT, self.lot, self.master.name, START)
		self.suppliers = test_suppliers()

	def test_row_actuals_sum_work_orders_per_supplier_by_lot_and_process(self):
		map_action(KNIT, PROCESS)
		first = insert_work_order(self.lot, self.suppliers[0], 10, 4)
		second = insert_work_order(self.lot, self.suppliers[0], 5, 5)
		insert_work_order(self.lot, self.suppliers[1], 7, 0)
		actuals = get_row_actuals(self.name)
		self.assertEqual(
			[(entry["supplier"], entry["delivered"], entry["received"]) for entry in actuals[KNIT]],
			[(self.suppliers[0], 15, 9), (self.suppliers[1], 7, 0)],
		)
		self.assertEqual(sorted(actuals[KNIT][0]["documents"]), sorted([first, second]))
		self.assertEqual(actuals[KNIT][0]["doctype"], "YRP Work Order")
		self.assertNotIn(YARN, actuals)

	def test_row_actuals_ignore_cancelled_draft_other_lots_and_processes(self):
		map_action(KNIT, PROCESS)
		insert_work_order(self.lot, self.suppliers[0], 10, 4, docstatus=2)
		insert_work_order(self.lot, self.suppliers[0], 10, 4, docstatus=0)
		insert_work_order(make_lot(), self.suppliers[0], 10, 4)
		insert_work_order(self.lot, self.suppliers[0], 10, 4, process="TA-TEST-OTHER")
		self.assertEqual(get_row_actuals(self.name), {})

	def test_purchase_order_lines_map_to_actions_by_item_group(self):
		map_action(YARN, item_groups=[ITEM_GROUP])
		insert_purchase_order(
			self.suppliers[0],
			[(self.lot, 100, 40, ITEM_GROUP, None), (self.lot, 50, 50, ITEM_GROUP, None)],
		)
		insert_purchase_order(self.suppliers[0], [(self.lot, 30, 0, "TA-TEST-OTHER-GROUP", None)])
		insert_purchase_order(self.suppliers[0], [(make_lot(), 30, 0, ITEM_GROUP, None)])
		insert_purchase_order(self.suppliers[0], [(self.lot, 30, 0, ITEM_GROUP, None)], docstatus=2)
		[entry] = get_row_actuals(self.name)[YARN]
		self.assertEqual(
			(entry["doctype"], entry["supplier"], entry["ordered"], entry["received"]),
			("Purchase Order", self.suppliers[0], 150, 90),
		)

	def test_purchase_order_line_without_item_group_uses_the_item_group_of_its_item(self):
		item, group = frappe.db.get_value("Item", {"item_group": ["is", "set"]}, ["name", "item_group"])
		map_action(YARN, item_groups=[group])
		insert_purchase_order(self.suppliers[1], [(self.lot, 20, 5, None, item)])
		[entry] = get_row_actuals(self.name)[YARN]
		self.assertEqual((entry["supplier"], entry["ordered"], entry["received"]), (self.suppliers[1], 20, 5))

	def test_chips_show_planned_without_work_and_unplanned_actuals(self):
		map_action(KNIT, PROCESS)
		set_planned_suppliers(self.name, KNIT, json.dumps(self.suppliers[:2]))
		insert_work_order(self.lot, self.suppliers[1], 8, 2)
		insert_work_order(self.lot, self.suppliers[2], 3, 0)
		chips = get_supplier_chips(self.name)[KNIT]
		self.assertEqual(
			[(chip["supplier"], chip["is_planned"], bool(chip["actuals"])) for chip in chips],
			[(self.suppliers[0], 1, False), (self.suppliers[1], 1, True), (self.suppliers[2], 0, True)],
		)
		self.assertEqual(get_supplier_chips(self.name)[YARN], [])
