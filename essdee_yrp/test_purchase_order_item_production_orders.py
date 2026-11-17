from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import purchase_order_against as against
from essdee_yrp.stock_item_extensions import get_entry_fields

MODULE = "essdee_yrp.purchase_order_against"
FIELD = against.ITEM_PRODUCTION_ORDER_FIELD
APPROVED = {"YARN", "CLOTH"}


def validated_rows(names):
	return [{"production_order": name, "item_name": f"ITEM-{name}"} for name in names]


def purchase_order(table=(), items=(), name=None, docstatus=0):
	"""Real unsaved Purchase Order; `items` are (item_code, production_order) pairs."""
	doc = frappe.new_doc("Purchase Order")
	doc.docstatus = docstatus
	for production_order in table:
		doc.append(against.PRODUCTION_ORDERS_FIELD, {"production_order": production_order, "item_name": "OLD"})
	for item_code, production_order in items:
		doc.append("items", {"item_code": item_code, FIELD: production_order})
	if name:
		doc.name = name
		doc.set("__islocal", 0)
	return doc


def table_names(doc):
	return against.get_production_order_names(doc.get(against.PRODUCTION_ORDERS_FIELD))


class TestItemProductionOrderSync(TestCase):
	def sync(self, doc):
		with (
			patch(f"{MODULE}.get_approval_item_codes", side_effect=lambda codes: {code for code in codes if code in APPROVED}),
			patch(f"{MODULE}.get_production_order_rows", side_effect=validated_rows) as resolve,
		):
			against.append_item_production_orders(doc)
		return resolve

	def test_missing_row_production_orders_are_appended_once_in_row_order(self):
		doc = purchase_order(items=[("YARN", "PPO-1"), ("CLOTH", "PPO-2"), ("YARN", "PPO-1"), ("YARN", "PPO-3")])
		resolve = self.sync(doc)
		self.assertEqual(table_names(doc), ["PPO-1", "PPO-2", "PPO-3"])
		resolve.assert_called_once_with(["PPO-1", "PPO-2", "PPO-3"])
		self.assertEqual(doc.production_orders[1].item_name, "ITEM-PPO-2")

	def test_existing_table_entries_are_never_removed(self):
		doc = purchase_order(table=["PPO-4", "PPO-2"], items=[("YARN", "PPO-1"), ("CLOTH", "PPO-2"), ("YARN", "PPO-3")])
		resolve = self.sync(doc)
		self.assertEqual(table_names(doc), ["PPO-4", "PPO-2", "PPO-1", "PPO-3"])
		resolve.assert_called_once_with(["PPO-1", "PPO-3"])
		self.assertEqual(doc.production_orders[1].item_name, "OLD")

	def test_sync_is_idempotent(self):
		doc = purchase_order(table=["PPO-4"], items=[("YARN", "PPO-1")])
		self.sync(doc)
		resolve = self.sync(doc)
		self.assertEqual(table_names(doc), ["PPO-4", "PPO-1"])
		resolve.assert_not_called()

	def test_table_is_kept_when_rows_have_no_production_order(self):
		doc = purchase_order(table=["PPO-4"], items=[("YARN", None), ("CLOTH", "")])
		resolve = self.sync(doc)
		self.assertEqual(table_names(doc), ["PPO-4"])
		resolve.assert_not_called()

	def test_purchase_order_without_any_production_order_is_untouched(self):
		doc = purchase_order(items=[("YARN", None), ("BUTTON", None)])
		resolve = self.sync(doc)
		self.assertEqual(table_names(doc), [])
		resolve.assert_not_called()

	def test_non_approved_item_rows_do_not_add_and_lose_their_production_order(self):
		doc = purchase_order(table=["PPO-4"], items=[("BUTTON", "PPO-9"), ("YARN", "PPO-1")])
		self.sync(doc)
		self.assertEqual(table_names(doc), ["PPO-4", "PPO-1"])
		self.assertFalse(doc.items[0].get(FIELD))
		self.assertEqual(doc.items[1].get(FIELD), "PPO-1")

	def test_invalid_row_production_order_fails_loudly(self):
		doc = purchase_order(items=[("YARN", "PPO-1")])
		with (
			patch(f"{MODULE}.get_approval_item_codes", return_value={"YARN"}),
			patch(f"{MODULE}.frappe.db.exists", return_value=False),
			self.assertRaises(frappe.DoesNotExistError),
		):
			against.append_item_production_orders(doc)
		self.assertEqual(table_names(doc), [])


class TestSavedTableAcceptsRowProductionOrders(TestCase):
	def check(self, doc, stored):
		with (
			patch(f"{MODULE}.get_stored_production_orders", return_value=stored),
			patch(f"{MODULE}.get_production_order_rows", side_effect=validated_rows) as resolve,
		):
			against.validate_purchase_order_against_unchanged(doc)
		return resolve

	def test_draft_may_add_production_orders_referenced_by_item_rows(self):
		doc = purchase_order(table=["PPO-4", "PPO-1"], items=[("YARN", "PPO-1")], name="PO-1")
		resolve = self.check(doc, ["PPO-4"])
		resolve.assert_called_once_with(["PPO-1"])
		self.assertEqual(doc.production_orders[1].item_name, "ITEM-PPO-1")

	def test_draft_may_not_add_production_orders_without_an_item_row(self):
		doc = purchase_order(table=["PPO-4", "PPO-5"], items=[("YARN", "PPO-1")], name="PO-1")
		with self.assertRaisesRegex(frappe.ValidationError, "Production Orders cannot be changed"):
			self.check(doc, ["PPO-4"])

	def test_draft_may_not_remove_or_reorder_saved_production_orders(self):
		for table in (["PPO-1"], ["PPO-5", "PPO-4", "PPO-1"]):
			doc = purchase_order(table=table, items=[("YARN", "PPO-1")], name="PO-1")
			with self.subTest(table=table), self.assertRaises(frappe.ValidationError):
				self.check(doc, ["PPO-4", "PPO-5"])

	def test_submitted_purchase_order_may_not_add_production_orders(self):
		doc = purchase_order(table=["PPO-4", "PPO-1"], items=[("YARN", "PPO-1")], name="PO-1", docstatus=1)
		with self.assertRaises(frappe.ValidationError):
			self.check(doc, ["PPO-4"])


class TestItemProductionOrderContract(TestCase):
	def test_item_field_is_an_optional_production_order_link_shown_for_approved_groups(self):
		field = frappe.get_meta("Purchase Order Item").get_field(FIELD)
		self.assertEqual((field.fieldtype, field.options, field.label), ("Link", "YRP Production Order", "Production Order"))
		self.assertFalse(field.reqd)
		self.assertTrue(field.no_copy)
		self.assertIn("production_order_item_groups", field.depends_on)
		self.assertIn("doc.item_group", field.depends_on)

	def test_hooks_append_before_the_unchanged_check(self):
		hooks = frappe.get_hooks("doc_events")["Purchase Order"]["validate"]
		self.assertLess(
			hooks.index(f"{MODULE}.append_item_production_orders"),
			hooks.index(f"{MODULE}.validate_purchase_order_against_unchanged"),
		)

	def test_item_groups_come_from_mrp_settings_and_reach_the_desk_onload(self):
		with patch(f"{MODULE}.get_approval_item_groups", return_value={"Yarn", "Cloth"}):
			self.assertEqual(against.get_production_order_item_groups(), ["Cloth", "Yarn"])
			doc = purchase_order()
			with patch(f"{MODULE}.can_manage_production_orders", return_value=False):
				against.set_production_order_onload(doc)
		self.assertEqual(doc.get_onload().production_order_item_groups, ["Cloth", "Yarn"])

	def test_web_editor_keeps_the_row_production_order_per_entry(self):
		self.assertIn(FIELD, get_entry_fields("Purchase Order"))

	def test_web_item_schema_says_whether_the_item_takes_a_production_order(self):
		from essdee_yrp.fabric_store import web_workspace as workspace

		for approved in (True, False):
			with (
				self.subTest(approved=approved),
				patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
				patch("essdee_yrp.cutting.web_workspace._get_stock_item_schema_data", return_value={"item": "ITEM"}),
				patch("essdee_yrp.fabric_store.web_workspace.is_approval_item", return_value=approved) as is_approval,
			):
				payload = workspace.get_purchase_order_item_schema("ITEM")
			self.assertIs(payload["is_production_order_item"], approved)
			is_approval.assert_called_once_with("ITEM")


class TestItemProductionOrderSiteData(IntegrationTestCase):
	"""Real Draft Purchase Order inside the test transaction."""

	def test_saving_a_draft_appends_the_row_production_order_and_keeps_the_rest(self):
		frappe.set_user("Administrator")
		open_orders = frappe.get_all(
			against.PRODUCTION_ORDER_DOCTYPE, filters={"docstatus": 1, "status": "Open"}, pluck="name", limit_page_length=2
		)
		name = frappe.get_value("Purchase Order", {"docstatus": 0, "is_yrp_managed": 1, "status": "Draft"}, "name")
		if len(open_orders) < 2 or not name:
			self.skipTest("Needs a Draft YRP Purchase Order and two open Production Orders.")
		kept, picked = open_orders
		frappe.db.delete(against.PRODUCTION_ORDER_ROW_DOCTYPE, {"parenttype": "Purchase Order", "parent": name})
		with patch(f"{MODULE}.get_live_request", return_value=None):
			against.update_purchase_order_production_orders(name, [kept])
		doc = frappe.get_doc("Purchase Order", name)
		doc.items[0].set(FIELD, picked)
		hooks = [hook for hook in frappe.get_hooks("doc_events")["Purchase Order"]["validate"] if hook.startswith("essdee_yrp.")]
		with patch(f"{MODULE}.get_approval_item_codes", return_value={doc.items[0].item_code}):
			for hook in hooks:
				frappe.get_attr(hook)(doc)
		self.assertEqual(table_names(doc), [kept, picked])
		self.assertEqual(doc.production_orders[1].item_name, frappe.db.get_value(against.PRODUCTION_ORDER_DOCTYPE, picked, "item"))


class TestWebDuplicateDropsRowProductionOrders(TestCase):
	def test_duplicate_editor_does_not_copy_row_production_orders(self):
		from essdee_yrp.fabric_store.documents.purchase_order import get_purchase_order_editor

		service = "essdee_yrp.fabric_store.documents.purchase_order"
		original = frappe._dict(items=[frappe._dict(item_code="YARN", qty=1, production_order="PPO-1")])
		doc = frappe._dict(doctype="Purchase Order", docstatus=0)
		doc.set = lambda key, value: doc.__setitem__(key, value)
		with (
			patch(f"{service}.frappe.has_permission", return_value=True),
			patch(f"{service}.frappe.new_doc", return_value=doc),
			patch(f"{service}._get_purchase_order", return_value=original),
			patch(f"{service}.group_items_for_ui", return_value=[]) as group_items,
			patch(f"{service}.get_stock_dimensions_for_ui", return_value=[]),
			patch(f"{service}.get_effective_fields", return_value=[]),
			patch(f"{service}.frappe.db.get_single_value", return_value=0),
		):
			get_purchase_order_editor(source={"duplicate_from": "PO-1"})
		self.assertEqual(group_items.call_args.args[0], [{"item_code": "YARN", "qty": 1}])
		self.assertEqual(original["items"][0].production_order, "PPO-1")


def lot_purchase_order(rows):
	"""Unsaved Purchase Order; `rows` are (item_code, lot, production_order)."""
	doc = frappe.new_doc("Purchase Order")
	for item_code, lot, production_order in rows:
		doc.append("items", {"item_code": item_code, "lot": lot, FIELD: production_order})
	return doc


LOT_PPOS = {"LOT-A": ["PPO-1"], "LOT-B": []}


class TestLotLimitsRowProductionOrder(TestCase):
	def validate(self, doc):
		with (
			patch(f"{MODULE}.get_approval_item_codes", side_effect=lambda codes: {code for code in codes if code in APPROVED}),
			patch(f"{MODULE}.get_lot_production_orders", side_effect=lambda lot: LOT_PPOS.get(lot, [])),
			patch(f"{MODULE}.get_production_order_rows", side_effect=validated_rows),
		):
			against.append_item_production_orders(doc)

	def test_row_production_order_must_be_one_linked_to_its_lot(self):
		doc = lot_purchase_order([("YARN", "LOT-A", "PPO-1"), ("YARN", "LOT-A", "PPO-2")])
		with self.assertRaises(frappe.ValidationError) as raised:
			self.validate(doc)
		message = str(raised.exception)
		for text in ("Row 2", "PPO-2", "LOT-A", "PPO-1"):
			self.assertIn(text, message)
		self.assertEqual(table_names(doc), [])

	def test_linked_production_order_passes(self):
		doc = lot_purchase_order([("YARN", "LOT-A", "PPO-1")])
		self.validate(doc)
		self.assertEqual(table_names(doc), ["PPO-1"])

	def test_rows_without_lot_or_with_an_unlinked_lot_take_any_production_order(self):
		doc = lot_purchase_order([("YARN", None, "PPO-7"), ("CLOTH", "LOT-B", "PPO-8")])
		self.validate(doc)
		self.assertEqual(table_names(doc), ["PPO-7", "PPO-8"])

	def test_non_approved_rows_are_cleared_before_the_lot_check(self):
		doc = lot_purchase_order([("BUTTON", "LOT-A", "PPO-9")])
		self.validate(doc)
		self.assertFalse(doc.items[0].get(FIELD))


class TestLotFiltersProductionOrderSearch(TestCase):
	def options(self, lot, linked):
		with (
			patch(f"{MODULE}.get_lot_production_orders", return_value=linked) as lot_orders,
			patch(f"{MODULE}.frappe.get_list", return_value=[frappe._dict(name="PPO-1", item="TEE")]) as get_list,
		):
			rows = against.search_production_orders("TEE", lot=lot)
		return rows, get_list.call_args.kwargs["filters"], lot_orders

	def test_lot_with_linked_production_orders_limits_the_search_to_them(self):
		rows, filters, _lot_orders = self.options("LOT-A", ["PPO-1"])
		self.assertEqual(filters, {"docstatus": 1, "status": ["!=", "Closed"], "name": ["in", ["PPO-1"]]})
		self.assertEqual(rows[0]["name"], "PPO-1")

	def test_lot_without_production_orders_or_no_lot_keeps_the_open_list(self):
		for lot in ("LOT-B", None):
			with self.subTest(lot=lot):
				_rows, filters, lot_orders = self.options(lot, [])
				self.assertEqual(filters, {"docstatus": 1, "status": ["!=", "Closed"]})
				if not lot:
					lot_orders.assert_not_called()

	def test_desk_query_reads_the_row_lot_filter(self):
		with patch(f"{MODULE}.get_production_order_options", return_value=[]) as options:
			against.production_order_query("YRP Production Order", "TEE", "name", 0, 20, {"lot": "LOT-A"})
		options.assert_called_once_with("TEE", 20, lot="LOT-A")


class TestLotProductionOrderSiteData(IntegrationTestCase):
	def test_real_lot_link_filters_search_and_validation(self):
		frappe.set_user("Administrator")
		linked = frappe.db.sql(
			"""select l.name, l.production_order from `tabSD YRP Lot` l
			join `tabYRP Production Order` p on p.name = l.production_order
			where p.docstatus = 1 and p.status = 'Open' limit 1"""
		)
		other = frappe.get_value(against.PRODUCTION_ORDER_DOCTYPE, {"docstatus": 1, "status": "Open"}, "name", order_by="creation desc")
		if not linked or not other or other == linked[0][1]:
			self.skipTest("Needs a Lot linked to an open Production Order and another open Production Order.")
		lot, production_order = linked[0]
		self.assertEqual(against.get_lot_production_orders(lot), [production_order])
		self.assertEqual([row["name"] for row in against.search_production_orders("", lot=lot)], [production_order])
		doc = lot_purchase_order([("YARN", lot, other)])
		with (
			patch(f"{MODULE}.get_approval_item_codes", return_value={"YARN"}),
			self.assertRaisesRegex(frappe.ValidationError, lot),
		):
			against.append_item_production_orders(doc)
