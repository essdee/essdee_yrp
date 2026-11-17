"""Auto actual dates for the finishing (Ironing + Packing) actions from packing GRNs."""

import frappe
from frappe.utils import flt

from essdee_yrp.finishing.packing import get_finishing_packing_summary
from essdee_yrp.finishing.status import get_finishing_plan_total_cutting, get_set_item_parts_count
from essdee_yrp.time_and_action.auto_date import (
	clear_auto_actual_date,
	get_actual_date_percentage,
	get_process_names,
	set_auto_actual_date,
)


def apply_packing_goods_received_note(finishing_doc, grn, cancelled: bool) -> None:
	"""Date the lot's finishing actions once packed pieces reach the threshold; clear auto dates once not."""
	percentage = get_actual_date_percentage()
	if not percentage or not grn.get("includes_packing") or not finishing_doc.work_order:
		return
	process_names = get_process_names(
		frappe.db.get_value("YRP Work Order", finishing_doc.work_order, "process_name")
	)
	if not process_names:
		return
	total = get_finishing_plan_total_cutting(finishing_doc)
	if is_packing_threshold_met(get_packed_pieces(finishing_doc), total, percentage):
		if not cancelled and not grn.get("is_return"):
			set_auto_actual_date(finishing_doc.lot, process_names, grn.posting_date)
	else:
		clear_auto_actual_date(finishing_doc.lot, process_names)


def get_packed_pieces(finishing_doc) -> float:
	"""Packed boxes converted to pieces, as the Finishing Plan dispatch totals convert dispatched boxes."""
	parts_count = get_set_item_parts_count(finishing_doc)
	summary = get_finishing_packing_summary(finishing_doc)
	if summary.dynamic_ratio_packing:
		return flt(summary.total_packed) * parts_count
	boxes = sum(flt(row.quantity) for row in finishing_doc.get("finishing_plan_grn_details") or [])
	return boxes * flt(finishing_doc.pieces_per_box) * parts_count


def is_packing_threshold_met(packed_pieces: float, total_cutting: float, percentage: float) -> bool:
	return flt(total_cutting) > 0 and flt(packed_pieces) >= flt(total_cutting) * flt(percentage) / 100
