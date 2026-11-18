from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import folding_lot
from essdee_yrp.setup import MRP_SCHEMA_ROLES

ROLE = "Folding Lot Manager"
PLAIN_USER = "folding-lot-plain@example.com"
FOLDING_USER = "folding-lot-manager@example.com"


def _ensure_user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.set("roles", [])
	user.add_roles(*roles)
	return email


def _sample_work_order():
	name = frappe.db.get_value(
		"YRP Work Order",
		{
			"docstatus": 1,
			"is_rework": 0,
			"supplier_address": ["is", "set"],
			"delivery_address": ["is", "set"],
			"process_cost": ["is", "set"],
		},
		"name",
		order_by="creation desc",
	)
	return frappe.get_doc("YRP Work Order", name)


class TestFoldingLotSetup(IntegrationTestCase):
	def test_role_is_created_on_install_and_shipped_as_fixture(self):
		from essdee_yrp import hooks

		fixture_roles = next(
			fixture["filters"][0][2] for fixture in hooks.fixtures if fixture["dt"] == "Role"
		)
		self.assertIn(ROLE, MRP_SCHEMA_ROLES)
		self.assertIn(ROLE, fixture_roles)

	def test_mrp_settings_folding_lot_role_defaults_to_manager(self):
		field = frappe.get_meta("SD YRP MRP Settings").get_field("folding_lot_role")
		self.assertEqual((field.fieldtype, field.options, field.default), ("Link", "Role", ROLE))


class FoldingLotTestCase(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("SD YRP MRP Settings", "folding_lot_role", ROLE)
		if not frappe.db.exists("Role", ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": ROLE}).insert(ignore_permissions=True)
		_ensure_user(PLAIN_USER, ["System Manager"])
		_ensure_user(FOLDING_USER, ["System Manager", ROLE])

	def tearDown(self):
		frappe.set_user("Administrator")

	def patch_process_cost(self):
		"""Stand in the sample Work Order's approved Process Cost for the folding item."""
		self.process_cost = patch(
			"essdee_yrp.overrides.work_order.EssdeeWorkOrder.get_receivable_process_cost",
			return_value=self.sample.process_cost,
		)
		self.process_cost.start()
		self.addCleanup(self.process_cost.stop)

	def make_lot(self, user=FOLDING_USER, **values):
		frappe.set_user(user)
		try:
			return frappe.get_doc(
				{
					"doctype": "SD YRP Lot",
					"lot_name": frappe.generate_hash(length=10),
					"is_folding_lot": 1,
					**values,
				}
			).insert()
		finally:
			frappe.set_user("Administrator")


class TestFoldingLotFlag(FoldingLotTestCase):
	def test_role_user_creates_folding_lot_without_item(self):
		lot = self.make_lot()
		self.assertTrue(folding_lot.is_folding_lot(lot.name))
		self.assertFalse(lot.item)

	def test_user_without_role_cannot_create_folding_lot(self):
		with self.assertRaises(frappe.PermissionError):
			self.make_lot(user=PLAIN_USER)

	def test_user_without_role_cannot_toggle_flag(self):
		lot = self.make_lot()
		frappe.set_user(PLAIN_USER)
		lot.reload()
		lot.is_folding_lot = 0
		with self.assertRaises(frappe.PermissionError):
			lot.save()

	def test_user_without_role_can_edit_other_fields(self):
		lot = self.make_lot()
		frappe.set_user(PLAIN_USER)
		lot.reload()
		lot.status = "Closed"
		lot.save()
		self.assertEqual(frappe.db.get_value("SD YRP Lot", lot.name, "status"), "Closed")

	def test_regular_lot_needs_no_role(self):
		lot = self.make_lot(user=PLAIN_USER, is_folding_lot=0)
		self.assertFalse(folding_lot.is_folding_lot(lot.name))

	def test_unset_role_blocks_folding_lot(self):
		frappe.db.set_single_value("SD YRP MRP Settings", "folding_lot_role", None)
		with self.assertRaises(frappe.PermissionError):
			self.make_lot()


class TestFoldingWorkOrder(FoldingLotTestCase):
	def setUp(self):
		super().setUp()
		self.lot = self.make_lot().name
		self.sample = _sample_work_order()
		self.patch_process_cost()

	def make_work_order(self, user=FOLDING_USER, submit=False):
		sample = self.sample
		deliverable = sample.deliverables[0]
		receivable = sample.receivables[0]
		frappe.set_user(user)
		try:
			doc = frappe.get_doc(
				{
					"doctype": "YRP Work Order",
					"lot": self.lot,
					"process_name": sample.process_name,
					"supplier": sample.supplier,
					"supplier_address": sample.supplier_address,
					"delivery_location": sample.delivery_location,
					"delivery_address": sample.delivery_address,
					"planned_start_date": frappe.utils.nowdate(),
					"planned_end_date": frappe.utils.nowdate(),
					"expected_delivery_date": frappe.utils.nowdate(),
					"deliverables": [
						{"item_variant": deliverable.item_variant, "qty": 10, "uom": deliverable.uom}
					],
					"receivables": [
						{"item_variant": receivable.item_variant, "qty": 10, "uom": receivable.uom}
					],
				}
			).insert()
			if submit:
				doc.submit()
			return doc
		finally:
			frappe.set_user("Administrator")

	def test_manual_rows_submit_without_production_detail(self):
		doc = self.make_work_order(submit=True)
		self.assertEqual(doc.docstatus, 1)
		self.assertFalse(doc.production_detail)
		self.assertTrue(doc.item)
		self.assertEqual({row.lot for row in doc.deliverables + doc.receivables}, {self.lot})
		self.assertEqual(doc.deliverables[0].pending_quantity, 10)

	def test_user_without_role_can_save_but_not_submit(self):
		doc = self.make_work_order(user=PLAIN_USER)
		self.assertEqual(doc.docstatus, 0)
		frappe.set_user(PLAIN_USER)
		with self.assertRaises(frappe.PermissionError):
			doc.submit()

	def test_submit_requires_an_approved_process_cost(self):
		doc = self.make_work_order()
		self.process_cost.stop()
		frappe.set_user(FOLDING_USER)
		with self.assertRaisesRegex(frappe.ValidationError, "Process Cost"):
			doc.submit()
		self.process_cost.start()

	def test_production_detail_is_cleared(self):
		doc = self.make_work_order()
		doc.production_detail = frappe.db.get_value("YRP Item Production Detail", {}, "name")
		folding_lot.validate_work_order(doc)
		self.assertFalse(doc.production_detail)


class TestFoldingLotEditors(FoldingLotTestCase):
	def test_boot_flags_folding_lot_role_for_desk(self):
		from essdee_yrp.boot import boot_session

		for user, expected in ((PLAIN_USER, False), (FOLDING_USER, True)):
			frappe.set_user(user)
			bootinfo = {"session_defaults": []}
			boot_session(bootinfo)
			self.assertIs(bootinfo["essdee_yrp_can_edit_folding_lot"], expected)

	def test_web_lot_form_locks_flag_without_role(self):
		from essdee_yrp.purchase.lot_editor import get_lot_form

		for user, locked in ((PLAIN_USER, True), (FOLDING_USER, False)):
			frappe.set_user(user)
			form = get_lot_form()
			field = next(field for field in form["fields"] if field["fieldname"] == "is_folding_lot")
			self.assertEqual(field["read_only"], locked)
			self.assertIn("is_folding_lot", form["values"])

	def test_web_lot_save_rejects_flag_without_role(self):
		from essdee_yrp.purchase.lot_editor import save_lot

		frappe.set_user(PLAIN_USER)
		values = {
			"lot_name": frappe.generate_hash(length=10),
			"is_folding_lot": 1,
			"item_details": [],
			"order_item_details": [],
			"lot_fabric_details": [],
		}
		with self.assertRaises(frappe.PermissionError):
			save_lot(values)


class TestFoldingWorkOrderWebEditor(FoldingLotTestCase):
	def setUp(self):
		super().setUp()
		self.lot = self.make_lot().name
		self.sample = _sample_work_order()
		self.patch_process_cost()

	def grouped(self, table, child_doctype):
		from yrp.stock.save_stock_items import group_items_for_ui

		groups = group_items_for_ui(self.sample.get(table)[:1], child_doctype)
		for group in groups:
			for item in group["items"]:
				item["dimensions"] = {}
		return groups

	def header(self):
		sample = self.sample
		return {
			"naming_series": "WO-",
			"lot": self.lot,
			"process_name": sample.process_name,
			"supplier": sample.supplier,
			"supplier_address": sample.supplier_address,
			"delivery_location": sample.delivery_location,
			"delivery_address": sample.delivery_address,
			"wo_date": frappe.utils.nowdate(),
			"planned_start_date": frappe.utils.nowdate(),
			"planned_end_date": frappe.utils.nowdate(),
			"expected_delivery_date": frappe.utils.nowdate(),
		}

	def test_selection_context_flags_folding_lot(self):
		from essdee_yrp.api.work_order import get_work_order_selection_context

		context = get_work_order_selection_context(self.lot, self.sample.process_name)
		self.assertTrue(context["is_folding_lot"])
		self.assertEqual(context["options"], [])

	def test_editor_reports_folding_lot(self):
		from essdee_yrp.fabric_store.documents.work_order import get_work_order_editor

		frappe.set_user(FOLDING_USER)
		editor = get_work_order_editor(source={"lot": self.lot})
		self.assertTrue(editor["is_folding_lot"])

	def test_saves_and_submits_manual_grouped_rows(self):
		from essdee_yrp.fabric_store.documents.work_order import save_work_order_document

		frappe.set_user(FOLDING_USER)
		values = {
			**self.header(),
			"deliverable_details": self.grouped("deliverables", "YRP Work Order Deliverables"),
			"receivable_details": self.grouped("receivables", "YRP Work Order Receivables"),
		}
		workspace = save_work_order_document(values, submit=True)
		doc = frappe.get_doc("YRP Work Order", workspace["record"]["name"])
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.deliverables[0].item_variant, self.sample.deliverables[0].item_variant)
		self.assertEqual(doc.receivables[0].lot, self.lot)

	def test_row_comments_persist_through_save_submit_and_print(self):
		from essdee_yrp.fabric_store.documents.work_order import (
			get_work_order_editor,
			save_work_order_document,
		)
		from essdee_yrp.print_helpers import get_work_order_challan_items

		deliverables = self.grouped("deliverables", "YRP Work Order Deliverables")
		receivables = self.grouped("receivables", "YRP Work Order Receivables")
		deliverables[0]["items"][0]["comments"] = "Fold in half"
		receivables[0]["items"][0]["comments"] = ""
		frappe.set_user(FOLDING_USER)
		values = {**self.header(), "deliverable_details": deliverables, "receivable_details": receivables}
		name = save_work_order_document(values)["record"]["name"]

		editor = get_work_order_editor(name)
		self.assertEqual(editor["deliverable_details"][0]["items"][0]["comments"], "Fold in half")
		editor["receivable_details"][0]["items"][0]["comments"] = "Pack flat"
		workspace = save_work_order_document(
			{
				**editor["values"],
				"deliverable_details": editor["deliverable_details"],
				"receivable_details": editor["receivable_details"],
			},
			name=name,
			submit=True,
			expected_modified=editor["modified"],
		)

		doc = frappe.get_doc("YRP Work Order", name)
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual({row.comments for row in doc.deliverables}, {"Fold in half"})
		self.assertEqual({row.comments for row in doc.receivables}, {"Pack flat"})
		self.assertEqual(workspace["matrices"]["deliverables"][0]["items"][0]["comments"], "Fold in half")
		printed = get_work_order_challan_items(doc, "deliverables")[0]["items"][0]
		self.assertEqual(printed["comments"], "Fold in half")
		html = frappe.get_print("YRP Work Order", name, "Essdee Work Order Receivables", no_letterhead=1)
		self.assertIn("Comments", html)
		self.assertIn("Pack flat", html)

	def test_item_schema_is_open_to_work_order_users(self):
		from essdee_yrp.fabric_store.documents.work_order import get_work_order_item_schema

		frappe.set_user(PLAIN_USER)
		self.assertEqual(get_work_order_item_schema(self.sample.item)["item"], self.sample.item)


class TestFoldingGoodsReceivedNoteConsumption(TestFoldingWorkOrder):
	def received_grn(self, work_order, quantity):
		receivable = work_order.receivables[0]
		grn = frappe.new_doc("YRP Goods Received Note")
		grn.update(
			{
				"against": "YRP Work Order",
				"against_id": work_order.name,
				"lot": self.lot,
				"from_warehouse": work_order.supplier,
				"posting_date": frappe.utils.nowdate(),
				"posting_time": "10:00:00",
			}
		)
		grn.append(
			"items", {"item_variant": receivable.item_variant, "quantity": quantity, "uom": receivable.uom}
		)
		grn.items[0].name = "received-row"
		return grn

	def deliver(self, work_order, quantity):
		row = work_order.deliverables[0]
		frappe.db.set_value(row.doctype, row.name, "pending_quantity", row.qty - quantity)

	def test_grn_uses_the_folding_plan(self):
		from essdee_yrp.overrides.goods_received_note import _new_consumption_plan_kind

		work_order = self.make_work_order(submit=True)
		self.assertEqual(_new_consumption_plan_kind(self.received_grn(work_order, 4)), "folding")

	def test_receipt_consumes_deliverables_in_proportion(self):
		work_order = self.make_work_order(submit=True)
		self.deliver(work_order, 10)
		plan = folding_lot.calculate_folding_consumption_plan(self.received_grn(work_order, 4))
		self.assertEqual(len(plan), 1)
		self.assertEqual(plan[0]["work_order_deliverable"], work_order.deliverables[0].name)
		self.assertEqual(plan[0]["item_variant"], work_order.deliverables[0].item_variant)
		self.assertEqual(plan[0]["quantity"], 4)
		self.assertEqual(plan[0]["dimensions"]["lot"], self.lot)

	def test_receipt_beyond_delivered_input_fails(self):
		work_order = self.make_work_order(submit=True)
		self.deliver(work_order, 3)
		with self.assertRaises(frappe.ValidationError):
			folding_lot.calculate_folding_consumption_plan(self.received_grn(work_order, 4))


class TestFoldingDocumentDefaults(TestFoldingWorkOrder):
	def test_dc_and_grn_defaults_are_open_to_every_user(self):
		from essdee_yrp.work_order_actions import (
			get_delivery_challan_defaults,
			get_goods_received_note_defaults,
		)

		work_order = self.make_work_order(submit=True)
		frappe.set_user(PLAIN_USER)
		self.assertEqual(get_delivery_challan_defaults(work_order.name)["lot"], self.lot)
		self.assertEqual(get_goods_received_note_defaults(work_order.name)["lot"], self.lot)


class TestFoldingProcessCost(TestFoldingWorkOrder):
	def test_process_cost_keeps_the_chosen_item_for_a_folding_lot(self):
		from essdee_yrp.process_cost import before_validate

		doc = frappe._dict(lot=self.lot, process_name=self.sample.process_name, item=self.sample.item, uom=None)
		before_validate(doc)
		self.assertEqual(doc.item, self.sample.item)
		self.assertEqual(doc.uom, frappe.db.get_value("Item", self.sample.item, "stock_uom"))
