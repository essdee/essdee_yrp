import frappe
from frappe import _
from yrp.attribute_read_context import attribute_read_scope

from essdee_yrp.fabric_program import fetch_fabric_program_details
from essdee_yrp.merch import lot_process_flow
from essdee_yrp.merch import lot_workspace as merch_lot_workspace
from essdee_yrp.merch.lot_process_data import LotFlowData
from essdee_yrp.purchase import lot_documents, lot_editor
from essdee_yrp.purchase import lot_workspace as purchase_lot_workspace

PLAN_DOCTYPES = {"ccr": "SD YRP Cutting Plan", "ocr": "SD YRP Finishing Plan"}
PLAN_FIELDS = {
	"ccr": ["name", "cp_status", "docstatus", "cutting_start_date", "creation"],
	"ocr": ["name", "fp_status", "finishing_start_date", "creation"],
}


def get_plan_access() -> dict[str, bool]:
	"""CCR / OCR shortcut visibility: read access on the Cutting / Finishing Plan doctype."""
	return {key: bool(frappe.has_permission(doctype, "read")) for key, doctype in PLAN_DOCTYPES.items()}


def get_lot_plans(lot: str, key: str) -> list[dict]:
	"""Non-cancelled Cutting or Finishing Plans of a lot, newest first."""
	doctype = PLAN_DOCTYPES[key]
	frappe.has_permission(doctype, "read", throw=True)
	return frappe.get_list(
		doctype,
		fields=PLAN_FIELDS[key],
		filters=[["lot", "=", lot], ["docstatus", "!=", 2]],
		order_by="creation desc",
		limit_page_length=100,
	)


def _require_existing(name):
	if not (name or "").strip():
		frappe.throw(_("Planning edits existing Lots only."), frappe.PermissionError)


@frappe.whitelist()
def get_lot_workspace(name: str):
	flow = LotFlowData(name)
	return {
		**purchase_lot_workspace.get_lot_workspace(name),
		"header": merch_lot_workspace.get_record_facts(flow.doc, purchase_lot_workspace.HEADER_FIELDS),
		"order_pieces": flow.order_pieces(),
		"plan_access": get_plan_access(),
	}


@frappe.whitelist()
def get_lot_cutting_plans(lot: str):
	return get_lot_plans(lot, "ccr")


@frappe.whitelist()
def get_lot_finishing_plans(lot: str):
	return get_lot_plans(lot, "ocr")


@frappe.whitelist()
def get_lot_process_flow(lot: str):
	return lot_process_flow.get_process_flow(lot)


@frappe.whitelist()
def get_lot_flow_context(lot: str) -> dict:
	"""Status, item and cloth programs shown beside a Lot process flow, without the full workspace."""
	doc = frappe.get_doc("SD YRP Lot", lot)
	doc.check_permission("read")
	with attribute_read_scope():
		programs = fetch_fabric_program_details(doc) if doc.get("lot_fabric_details") else []
	return {
		"name": doc.name,
		"status": doc.status or "Open",
		"item": doc.item,
		"fabrics": [{"cloth_item": row["cloth_item"], "program": row.get("program") or []} for row in programs],
	}


@frappe.whitelist()
def get_lot_step_detail(lot: str, key: str):
	return lot_process_flow.get_step_detail(lot, key)


@frappe.whitelist()
def get_lot_work_order_detail(work_order: str):
	return lot_process_flow.get_work_order_detail(work_order)


@frappe.whitelist()
def get_lot_documents(lot: str):
	return lot_documents.get_lot_documents(lot)


@frappe.whitelist()
def get_lot_document(lot: str, doctype: str, name: str):
	return lot_documents.get_lot_document(lot, doctype, name)


@frappe.whitelist()
def get_lot_form(name: str | None = None):
	_require_existing(name)
	return lot_editor.get_lot_form(name)


@frappe.whitelist()
def get_lot_production_detail_context(
	production_detail: str, item: str, production_order: str | None = None,
):
	return lot_editor.get_lot_production_detail_context(production_detail, item, production_order)


@frappe.whitelist()
def get_lot_production_order_item(production_order: str):
	return lot_editor.get_lot_production_order_item(production_order)


@frappe.whitelist(methods=["POST"])
def save_lot(values, name: str | None = None, expected_modified: str | None = None):
	_require_existing(name)
	return lot_editor.save_lot(values, name, expected_modified)
