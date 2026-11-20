import json
import re
from unittest.mock import Mock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet import approve_grammage
from essdee_yrp.merch.laysheet_grammage_telegram import (
	DOCTYPE,
	ROUTE_VALUES,
	apply_route_values,
)
from essdee_yrp.telegram_approval import service
from essdee_yrp.telegram_approval.api import _process_callback_query
from essdee_yrp.telegram_approval.renderers import render_message
from essdee_yrp.test_cls_grammage_approval import make_user

APPROVER = "cls.grammage.telegram.approver@test.local"
READER = "cls.grammage.telegram.reader@test.local"
APPROVER_TELEGRAM_ID = "990001"
READER_TELEGRAM_ID = "990002"
CHAT_ID = "-100555"
MESSAGE_ID = "77"


class TestLaySheetGrammageTelegram(IntegrationTestCase):
	"""Cutting LaySheet grammage approvals sent to and approved from Telegram."""

	def setUp(self):
		name = frappe.db.get_value(
			DOCTYPE, {"status": "Approval Pending", "docstatus": 0, "cutting_plan": ["is", "set"]}, "name"
		)
		if not name:
			self.skipTest("No Approval Pending Cutting LaySheet on this site")
		self.laysheet = frappe.get_doc(DOCTYPE, name)
		settings = frappe.get_single("SD YRP MRP Settings")
		if "Merch Manager" not in {row.role for row in settings.cls_grammage_approval_roles}:
			settings.append("cls_grammage_approval_roles", {"role": "Merch Manager"})
			settings.save(ignore_permissions=True)
		make_user(APPROVER, ["Merch User", "Merch Manager"])
		make_user(READER, ["Merch User"])
		frappe.db.set_value("User", APPROVER, "telegram_user_id", APPROVER_TELEGRAM_ID)
		frappe.db.set_value("User", READER, "telegram_user_id", READER_TELEGRAM_ID)
		self.client = Mock()
		self.client.get_chat_member.return_value = {"status": "member"}
		self.client.send_message.return_value = {"message_id": MESSAGE_ID}
		for target in (
			"essdee_yrp.telegram_approval.api.get_client",
			"essdee_yrp.telegram_approval.service.get_client",
		):
			patcher = patch(target, return_value=self.client)
			patcher.start()
			self.addCleanup(patcher.stop)
		enqueue = patch("essdee_yrp.telegram_approval.service.frappe.enqueue")
		self.enqueue = enqueue.start()
		self.addCleanup(enqueue.stop)

	def tearDown(self):
		frappe.set_user("Administrator")

	def route(self, **overrides):
		route = frappe._dict(ROUTE_VALUES, enabled=1, group_chat_id=CHAT_ID, name="ROUTE-LS")
		apply_route_values(route)
		route.update(overrides)
		return route

	def make_request(self):
		route = self.route()
		return frappe.get_doc(
			{
				"doctype": service.REQUEST_DOCTYPE,
				"reference_doctype": DOCTYPE,
				"reference_name": self.laysheet.name,
				"route_row": route.name,
				"route_snapshot": json.dumps(service.get_route_snapshot(route), sort_keys=True),
				"state_field": "status",
				"source_value": "Approval Pending",
				"group_chat_id": CHAT_ID,
				"telegram_message_id": MESSAGE_ID,
				"message_text": "LAYSHEET GRAMMAGE APPROVAL",
				"status": "Pending",
			}
		).insert(ignore_permissions=True)

	def tap(self, telegram_user_id, request_name):
		self.client.reset_mock()
		_process_callback_query(
			{
				"id": "CB-1",
				"data": f"ta:{request_name}:a",
				"message": {"chat": {"id": CHAT_ID}, "message_id": MESSAGE_ID},
				"from": {"id": telegram_user_id},
			}
		)

	def test_message_lists_laysheet_fields(self):
		message = render_message(self.laysheet, self.route())
		for expected in (
			f"Lot: {self.laysheet.lot}",
			f"Cutting Plan: {self.laysheet.cutting_plan}",
			f"Lay No: {self.laysheet.lay_no}",
			f"Item: {self.laysheet.item}",
			"Required Weight:",
			"Actual Weight:",
			"Difference:",
			"Tolerance:",
		):
			self.assertIn(expected, message)
		for removed in ("LaySheet:", "Work Order:", "LaySheet Date:", "Open:"):
			self.assertNotIn(removed, message)

	def test_settings_fill_laysheet_route_values(self):
		settings = frappe.get_single(service.SETTINGS_DOCTYPE)
		settings.set("routes", [])
		settings.append("routes", {"enabled": 1, "reference_doctype": DOCTYPE, "group_chat_id": CHAT_ID})
		settings.validate()
		route = settings.routes[0]
		self.assertEqual((route.process_type, route.trigger_field, route.trigger_value), ("Field State", "status", "Approval Pending"))
		self.assertEqual((route.approve_action, route.reject_action), ("Approve", ""))
		self.assertEqual((route.target_field, route.approve_value), ("status", "Bundles Generated"))
		self.assertIn("LAYSHEET GRAMMAGE APPROVAL", route.message_template)

	def test_approval_pending_queues_telegram_request(self):
		settings = frappe._dict(enabled=1, routes=[self.route()])
		self.laysheet._doc_before_save = frappe._dict(status="Bundles Generated")
		with patch("essdee_yrp.telegram_approval.service.get_settings", return_value=settings):
			service.handle_document_event(self.laysheet)
		self.enqueue.assert_any_call(
			"essdee_yrp.telegram_approval.service.create_and_send_approval",
			queue="short",
			enqueue_after_commit=True,
			doctype=DOCTYPE,
			docname=self.laysheet.name,
			route_row="ROUTE-LS",
		)

	def test_send_posts_only_approve_button_to_route_group(self):
		settings = frappe._dict(enabled=1, routes=[self.route()])
		with patch("essdee_yrp.telegram_approval.service.get_settings", return_value=settings):
			request_name = service.create_and_send_approval(DOCTYPE, self.laysheet.name, "ROUTE-LS")
		chat_id, text = self.client.send_message.call_args.args
		buttons = self.client.send_message.call_args.kwargs["reply_markup"]["inline_keyboard"][0]
		self.assertEqual(chat_id, CHAT_ID)
		self.assertIn(f"Lot: {self.laysheet.lot}", text)
		self.assertEqual([button["text"] for button in buttons], ["Approve"])
		self.assertEqual(frappe.db.get_value(service.REQUEST_DOCTYPE, request_name, "status"), "Pending")

	def test_callback_approves_as_mapped_user(self):
		request = self.make_request()
		self.tap(APPROVER_TELEGRAM_ID, request.name)
		status, approved_by = frappe.db.get_value(DOCTYPE, self.laysheet.name, ["status", "approved_by"])
		self.assertEqual((status, approved_by), ("Bundles Generated", APPROVER))
		request.reload()
		self.assertEqual((request.status, request.frappe_user), ("Approved", APPROVER))
		text = self.client.edit_message.call_args.args[2]
		self.assertRegex(text, r"Approved by .+ at \d{2}-\d{2}-\d{4} \d{2}:\d{2}$")
		self.assertEqual(self.client.edit_message.call_args.kwargs["reply_markup"], {"inline_keyboard": []})

	def test_callback_refuses_user_without_grammage_role(self):
		request = self.make_request()
		self.tap(READER_TELEGRAM_ID, request.name)
		self.assertEqual(frappe.db.get_value(DOCTYPE, self.laysheet.name, "status"), "Approval Pending")
		self.assertEqual(frappe.db.get_value(service.REQUEST_DOCTYPE, request.name, "status"), "Pending")
		alert = self.client.answer_callback_query.call_args.args
		self.assertIn("required role", alert[1])
		self.assertTrue(alert[2])
		self.client.edit_message.assert_not_called()

	def test_repeat_tap_after_approval_is_idempotent(self):
		request = self.make_request()
		self.tap(APPROVER_TELEGRAM_ID, request.name)
		self.tap(APPROVER_TELEGRAM_ID, request.name)
		self.assertIn("already approved", self.client.answer_callback_query.call_args.args[1])
		self.client.edit_message.assert_not_called()
		self.assertEqual(frappe.db.get_value(service.REQUEST_DOCTYPE, request.name, "frappe_user"), APPROVER)

	def test_web_approval_closes_telegram_message(self):
		request = self.make_request()
		settings = frappe._dict(enabled=1, routes=[self.route()])
		frappe.set_user(APPROVER)
		with patch("essdee_yrp.telegram_approval.service.get_settings", return_value=settings):
			approve_grammage(self.laysheet.name)
		frappe.set_user("Administrator")
		request.reload()
		self.assertEqual((request.status, request.frappe_user), ("Approved", APPROVER))
		self.enqueue.assert_any_call(
			"essdee_yrp.telegram_approval.service.finish_request",
			queue="short",
			enqueue_after_commit=True,
			request_name=request.name,
			result_label="Approve",
			frappe_user=APPROVER,
		)

	def test_finished_laysheet_message_reads_approved_by_at_time(self):
		request = frappe._dict(
			reference_doctype=DOCTYPE, status="Approved", telegram_message_id=MESSAGE_ID,
			message_text="LAYSHEET", group_chat_id=CHAT_ID, name="REQ",
		)
		service.finish_request_message(request, "Approve", APPROVER)
		text = self.client.edit_message.call_args.args[2]
		self.assertTrue(re.search(r"\nApproved by .+ at \d{2}-\d{2}-\d{4} \d{2}:\d{2}$", text))


class TestBulkLaySheetApprovalTrigger(IntegrationTestCase):
	"""The bulk LaySheet print path sets Approval Pending with db_set, so it must queue Telegram itself."""

	def test_bulk_print_out_of_tolerance_queues_telegram(self):
		module = "essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_bulk_lay_sheets.sd_yrp_cutting_bulk_lay_sheets"
		laysheet = Mock(name="laysheet", piece_weight=0.3, required_pcs_weight=0.2, approved_by=None)
		laysheet.name = "CLS-TEST"
		with (
			patch(f"{module}.get_bulk_doc", return_value=frappe._dict(name="BULK-TEST")),
			patch(f"{module}.get_entry", return_value=frappe._dict(cutting_laysheet="CLS-TEST")),
			patch(f"{module}.frappe.get_doc", return_value=laysheet),
			patch(f"{module}.validate_bulk_print_prerequisites"),
			patch(f"{module}.validate_cutting_plan_stock"),
			patch(f"{module}.refresh_bulk_status"),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.get_laysheet_piece_weight_tolerance",
				return_value=0.003,
			),
			patch(f"{module}.handle_document_event") as handle,
		):
			from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_bulk_lay_sheets import (
				sd_yrp_cutting_bulk_lay_sheets,
			)

			result = sd_yrp_cutting_bulk_lay_sheets.get_label_print_context("BULK-TEST", "ROW-1")
		self.assertTrue(result["approval_required"])
		laysheet.db_set.assert_called_once_with("status", "Approval Pending")
		handle.assert_called_once_with(laysheet)
