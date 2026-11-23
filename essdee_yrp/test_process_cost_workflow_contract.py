import json
from pathlib import Path

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.api.workflow import get_active_workflow


class TestProcessCostWorkflowContract(UnitTestCase):
	def test_essdee_does_not_own_process_cost_workflow_state_field(self):
		fixture_path = frappe.get_app_path("essdee_yrp", "fixtures", "custom_field.json")
		with open(fixture_path, encoding="utf-8") as fixture_file:
			custom_fields = {row["name"] for row in json.load(fixture_file)}

		self.assertNotIn("Process Cost-workflow_state", custom_fields)

	def test_live_process_cost_workflow_uses_yrp_managed_field(self):
		workflow = frappe.get_doc("Workflow", "Process Cost Workflow")
		self.assertEqual(workflow.document_type, "YRP Process Cost")
		self.assertEqual(workflow.workflow_state_field, "workflow_state")
		transitions = {
			(row.state, row.action, row.next_state) for row in workflow.transitions
		}
		self.assertIn(("Draft", "Submit", "Approval Pending"), transitions)
		self.assertIn(("Approval Pending", "Approve", "Approved"), transitions)
		self.assertIn(("Approval Pending", "Reject", "Rejected"), transitions)

		field = frappe.get_meta("YRP Process Cost").get_field("workflow_state")
		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Workflow State")

	def test_active_workflow_contract_is_server_authoritative(self):
		contract = get_active_workflow("YRP Process Cost")
		self.assertEqual(contract["name"], "Process Cost Workflow")
		self.assertEqual(contract["state_field"], "workflow_state")
		self.assertIn("Approval Pending", contract["states"])
		self.assertIn("Approved", contract["states"])

		self.assertIsNone(get_active_workflow("SD YRP Lot"))

	def test_web_uses_workflow_actions_exclusively(self):
		source = Path(frappe.get_app_path("essdee_yrp")).parent / "frontend" / "src" / "components"
		dialog = (source / "documents" / "DocumentTransactionDialog.vue").read_text(encoding="utf-8")
		list_view = (source / "common" / "ListView.vue").read_text(encoding="utf-8")

		self.assertIn("getActiveWorkflow(props.doctype)", dialog)
		self.assertIn('v-if="payload.permissions?.can_submit && workflowReady && !activeWorkflow"', dialog)
		self.assertIn('v-if="payload.permissions?.can_cancel && workflowReady && !activeWorkflow"', dialog)
		self.assertIn("getActiveWorkflow(doctype)", list_view)
		self.assertIn("const canBulkLifecycle = computed(() => workflowReady.value && !activeWorkflow.value", list_view)
