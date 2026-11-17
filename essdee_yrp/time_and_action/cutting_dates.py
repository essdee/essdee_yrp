"""Auto actual date for the Cutting action, from the lot's Cutting Plans (requirement 34)."""

import frappe
from frappe.utils import getdate

from essdee_yrp.time_and_action.auto_date import (
	LOG_TITLE,
	clear_auto_actual_date,
	get_actual_date_percentage,
	get_process_names,
	set_auto_actual_date,
)
from essdee_yrp.time_and_action.work_order_dates import get_cutting_process

CUTTING_PLAN = "SD YRP Cutting Plan"
COMPLETED = "Completed"


def on_update_after_submit(cutting_plan, method=None):
	apply_cutting_plan(cutting_plan.name)


def on_cancel(cutting_plan, method=None):
	apply_cutting_plan(cutting_plan.name)


def apply_cutting_plan(cutting_plan: str) -> None:
	"""Date the lot's cutting actions once every plan is Completed; clear auto dates once one is not."""
	if not get_actual_date_percentage():
		return
	plan = frappe.db.get_value(CUTTING_PLAN, cutting_plan, ["lot", "production_detail"], as_dict=True)
	cutting_process = get_cutting_process(plan) if plan and plan.lot else None
	if not cutting_process:
		return
	process_names = get_process_names(cutting_process)
	plans = frappe.get_all(
		CUTTING_PLAN,
		filters={"lot": plan.lot, "docstatus": 1},
		fields=["name", "cp_status", "cutting_end_date"],
	)
	if not is_cutting_completed(plans):
		clear_auto_actual_date(plan.lot, process_names)
		return
	end_date = get_cutting_end_date(plans)
	if end_date:
		set_auto_actual_date(plan.lot, process_names, end_date)
		return
	undated = ", ".join(row.name for row in plans if not row.cutting_end_date)
	frappe.log_error(LOG_TITLE, f"{plan.lot}: Cutting Plan {undated} has no Cutting End Date")


def is_cutting_completed(plans) -> bool:
	"""True when the lot has submitted plans and every one is Completed."""
	return bool(plans) and all(row.get("cp_status") == COMPLETED for row in plans)


def get_cutting_end_date(plans):
	"""The latest Cutting End Date, or None when any plan has none."""
	if not plans or any(not row.get("cutting_end_date") for row in plans):
		return None
	return max(getdate(row.get("cutting_end_date")) for row in plans)
