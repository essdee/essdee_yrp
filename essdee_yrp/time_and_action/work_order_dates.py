"""Auto actual dates from Work Order GRNs, for every process except cutting and finishing packing."""

import json

import frappe
from frappe.utils import flt

from essdee_yrp.time_and_action.auto_date import (
	clear_auto_actual_date,
	get_actual_date_percentage,
	get_process_names,
	set_auto_actual_date,
)

WORK_ORDER = "YRP Work Order"


def on_goods_received_note_submit(grn, method=None):
	apply_goods_received_note(grn, cancelled=False)


def on_goods_received_note_cancel(grn, method=None):
	apply_goods_received_note(grn, cancelled=True)


def apply_goods_received_note(grn, cancelled: bool) -> None:
	"""Date the lot's process actions once the threshold is met; clear auto dates once it is not."""
	percentage = get_actual_date_percentage()
	work_order = get_work_order(grn) if percentage else None
	if not work_order:
		return
	process_names = get_process_names(work_order.process_name)
	if get_cutting_process(work_order) in process_names:
		return
	if is_threshold_met(get_cut_rows(work_order.lot), get_calculated_rows(work_order), percentage):
		if not cancelled and not grn.get("is_return"):
			set_auto_actual_date(work_order.lot, process_names, grn.posting_date)
	else:
		clear_auto_actual_date(work_order.lot, process_names)


def get_work_order(grn):
	"""The non-rework Work Order behind `grn`, or None when this path does not own the GRN."""
	if grn.get("against") != WORK_ORDER or not grn.get("against_id") or grn.get("is_rework"):
		return None
	if grn.get("includes_packing") or grn.get("from_finishing"):
		return None
	work_order = frappe.db.get_value(
		WORK_ORDER,
		grn.against_id,
		["lot", "process_name", "is_rework", "production_detail"],
		as_dict=True,
	)
	if not work_order or work_order.is_rework or not work_order.lot or not work_order.process_name:
		return None
	return work_order


def get_cutting_process(work_order) -> str | None:
	if not work_order.production_detail:
		return None
	return frappe.db.get_value("YRP Item Production Detail", work_order.production_detail, "cutting_process")


def get_cut_rows(lot: str) -> list:
	return frappe.get_all(
		"SD YRP Lot Order Detail",
		filters={"parent": lot, "parenttype": "SD YRP Lot", "parentfield": "lot_order_details"},
		fields=["item_variant", "set_combination", "cut_qty"],
	)


def get_calculated_rows(work_order) -> list:
	"""Calculated items of every submitted, non-rework Work Order of the same lot and process."""
	work_orders = frappe.get_all(
		WORK_ORDER,
		filters={
			"lot": work_order.lot,
			"process_name": work_order.process_name,
			"docstatus": 1,
			"is_rework": 0,
		},
		pluck="name",
	)
	if not work_orders:
		return []
	return frappe.get_all(
		"YRP Work Order Calculated Item",
		filters={"parenttype": WORK_ORDER, "parent": ["in", work_orders]},
		fields=["item_variant", "set_combination", "delivered_quantity", "received_qty"],
	)


def get_item_key(row) -> tuple:
	set_combination = frappe.parse_json(row.get("set_combination")) or {}
	return row.get("item_variant"), json.dumps(set_combination, sort_keys=True, separators=(",", ":"))


def is_threshold_met(cut_rows, calculated_rows, percentage: float) -> bool:
	"""Every colour/size/set part with cut qty has delivered and received ≥ `percentage` % of it."""
	cut = {}
	for row in cut_rows:
		cut[get_item_key(row)] = cut.get(get_item_key(row), 0) + flt(row.get("cut_qty"))
	totals = {}
	for row in calculated_rows:
		delivered, received = totals.get(get_item_key(row), (0, 0))
		totals[get_item_key(row)] = (
			delivered + flt(row.get("delivered_quantity")),
			received + flt(row.get("received_qty")),
		)
	required = {key: qty * flt(percentage) / 100 for key, qty in cut.items() if qty > 0}
	if not required:
		return False
	return all(min(totals.get(key, (0, 0))) >= qty for key, qty in required.items())
