import json
import time

import frappe
from frappe.utils import now_datetime
from frappe.utils.background_jobs import is_job_enqueued

from essdee_yrp.valuation_tree.lot import LotValuation

CACHE_DOCTYPE = "SD YRP Lot Valuation"
ACTIVE_STATUSES = ("Queued", "Running")


def job_id_for(lot):
	return f"lot-valuation::{lot}"


def require_access(lot):
	frappe.only_for("System Manager")
	frappe.has_permission("SD YRP Lot", "read", lot, throw=True)


@frappe.whitelist()
def enqueue_lot_valuation(lot: str) -> dict:
	"""Queue one background valuation for the Lot; a queued or running job for the same Lot is reused."""
	require_access(lot)
	state = get_cache(lot)
	job_id = job_id_for(lot)
	if state and state.status in ACTIVE_STATUSES and is_job_enqueued(job_id):
		return get_lot_valuation(lot)
	values = {
		"status": "Queued",
		"job_id": job_id,
		"requested_by": frappe.session.user,
		"requested_at": now_datetime(),
		"error": None,
	}
	if state:
		frappe.db.set_value(CACHE_DOCTYPE, lot, values, update_modified=False)
	else:
		frappe.get_doc({"doctype": CACHE_DOCTYPE, "lot": lot, **values}).insert(ignore_permissions=True)
	frappe.enqueue(
		"essdee_yrp.valuation_tree.api.run_lot_valuation",
		queue="long",
		timeout=1800,
		job_id=job_id,
		deduplicate=True,
		enqueue_after_commit=True,
		lot=lot,
	)
	return get_lot_valuation(lot)


@frappe.whitelist()
def get_lot_valuation(lot: str) -> dict:
	"""Status of the Lot's valuation job and its last computed tree; never computes."""
	require_access(lot)
	state = get_cache(lot, with_result=True)
	if not state:
		return {"lot": lot, "status": "Not Calculated", "result": None}
	return {
		"lot": lot,
		"status": state.status,
		"requested_by": state.requested_by,
		"requested_at": state.requested_at,
		"computed_at": state.computed_at,
		"duration": state.duration,
		"error": state.error,
		"result": json.loads(state.result) if state.result else None,
	}


def get_cache(lot, with_result=False):
	fields = ["name", "status", "requested_by", "requested_at", "computed_at", "duration", "error"]
	return frappe.db.get_value(
		CACHE_DOCTYPE, lot, [*fields, "result"] if with_result else fields, as_dict=True
	)


def run_lot_valuation(lot):
	"""Background job: build the tree and store it as the Lot's last result."""
	frappe.db.set_value(CACHE_DOCTYPE, lot, "status", "Running", update_modified=False)
	frappe.db.commit()
	started = time.monotonic()
	try:
		result = LotValuation(lot).build()
	except Exception:
		frappe.db.rollback()
		frappe.db.set_value(
			CACHE_DOCTYPE, lot, {"status": "Failed", "error": frappe.get_traceback()}, update_modified=False
		)
		frappe.db.commit()
		raise
	frappe.db.set_value(
		CACHE_DOCTYPE,
		lot,
		{
			"status": "Completed",
			"result": json.dumps(result, default=str, separators=(",", ":")),
			"computed_at": now_datetime(),
			"duration": round(time.monotonic() - started, 2),
			"error": None,
		},
		update_modified=False,
	)
	frappe.db.commit()
