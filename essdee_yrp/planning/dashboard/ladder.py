from frappe.utils import cint, flt

from essdee_yrp.merch import lot_process_rules as rules
from essdee_yrp.planning.reports.production_quantities import expand_processes

LADDER = [
	"Fabric not received",
	"Waiting for cutting",
	"In cutting",
	"Waiting for sewing",
	"In sewing",
	"Ready for packing",
	"Packing in progress",
	"Dispatched",
]
NO_WORK_ORDER = "No Work Order yet"
PO_CREATED = "PO Created"
MATERIAL_RECEIVED = "Yarn / Fabric Received"
STATUS_ORDER = [NO_WORK_ORDER, PO_CREATED, MATERIAL_RECEIVED, *LADDER]
CUTTING_PROCESS = "Cutting"
CUT_STATUSES = ("Completed", "Cut Panel Dispatch Pending")
CUTTING_PLAN_RANK = {
	"Completed": 7,
	"Cut Panel Dispatch Pending": 6,
	"Partially Completed": 5,
	"Cutting In Progress": 4,
	"Ready to Cut": 3,
	"Fabric Partially Received": 2,
	"Planned": 1,
}
MATCH_TOLERANCE = 0.1
DISPATCHED_SHARE = 0.9
SEWN_SHARE = 0.9
PURCHASE_RECEIVED_SHARE = 0.9


def get_basis(planned, cut):
	"""Lot pieces the ladder measures against: cut pieces once cut, else planned pieces."""
	return flt(cut) or flt(planned)


def get_balance(ppo_quantity, dispatch, to_alternative):
	"""The lot's share of PPO pieces not yet dispatched; pieces moved to an alternative lot count as dispatched."""
	return flt(ppo_quantity) - flt(dispatch) - flt(to_alternative)


def get_best_cutting_status(statuses):
	return max(statuses, key=lambda status: CUTTING_PLAN_RANK.get(status, 0)) if statuses else ""


def get_purchase_status(ordered, received):
	"""PO Created below 90% of the yarn / fabric PO quantity received, else Yarn / Fabric Received; "" with no such PO."""
	if flt(ordered) <= 0:
		return ""
	return MATERIAL_RECEIVED if flt(received) / flt(ordered) >= PURCHASE_RECEIVED_SHARE else PO_CREATED


def is_before_cutting(status):
	"""Fabric not received or a fabric process name: the lot has Work Orders but no cut yet."""
	return status == "Fabric not received" or status not in STATUS_ORDER


def get_po_created_pieces(status, purchase_status, basis, ordered, moved):
	"""Lot pieces still on PO for a lot already in a fabric stage: basis less the PO share moved into Work Orders."""
	if purchase_status != PO_CREATED or not is_before_cutting(status):
		return 0.0
	return flt(basis) * max(0.0, 1 - flt(moved) / flt(ordered))


def get_lot_status(facts):
	"""First matching rung, top (Dispatched) to bottom (Fabric not received); a fabric process name sits below Waiting for cutting.

	Pieces moved to an alternative lot count as dispatched.
	"""
	if not facts["has_work_order"] and not facts["has_cutting_plan"]:
		return facts["purchase_status"] or NO_WORK_ORDER
	basis = get_basis(facts["planned"], facts["cut"])
	dispatch = flt(facts["dispatch"]) + flt(facts["to_alternative"])
	if basis and dispatch / basis > DISPATCHED_SHARE:
		return "Dispatched"
	if flt(facts["pack_delivered"]) > 0 or dispatch > 0:
		return "Packing in progress"
	if basis and flt(facts["sewing_received"]) / basis >= SEWN_SHARE:
		return "Ready for packing"
	if flt(facts["sewing_delivered"]) > 0 or flt(facts["sewing_received"]) > 0:
		return "In sewing"
	if facts["cutting_status"] in CUT_STATUSES:
		return "Waiting for sewing"
	if cint(facts["lay_sheets"]) or facts["is_cutting_delivered"]:
		return "In cutting"
	if facts["has_cutting_plan"] and facts["has_cutting_work_order"]:
		return "Waiting for cutting"
	return facts["fabric_process"] or "Fabric not received"


def get_status_rank(status, fabric_step):
	"""Ladder position ×100, No Work Order yet lowest; a fabric process sits between Fabric not received and Waiting for cutting."""
	if status in STATUS_ORDER:
		return STATUS_ORDER.index(status) * 100
	return STATUS_ORDER.index("Fabric not received") * 100 + 1 + fabric_step


def get_fabric_steps(routes):
	"""{fabric process: furthest step} over the lot's cloth routes; each route is a process list in sequence order."""
	steps = {}
	for route in routes:
		for step, process in enumerate(route):
			steps[process] = max(step, steps.get(process, step))
	return steps


def get_fabric_process(orders, steps):
	"""(process, step) of the furthest fabric route process with a Work Order; ("", 0) when none."""
	reached = {order["process_name"] for order in orders} & set(steps)
	if not reached:
		return "", 0
	process = max(reached, key=lambda name: (steps[name], name))
	return process, steps[process]


def get_sewing_processes(setting, details, used_processes):
	"""Work Order processes that are the sewing setting or a group containing it."""
	if not setting:
		return []
	return sorted(process for process in set(used_processes) if setting in expand_processes(process, details))


def get_lot_quantities(orders, get_received, sewing):
	"""Cut, Stitching and Packed pieces of one lot; `get_received(orders)` totals what the Work Orders received, each once."""
	unique = list({order["name"]: order for order in orders}.values())

	def total(matches):
		return flt(get_received([order for order in unique if matches(order)]))

	return {
		"cut": total(lambda order: order["process_name"] == CUTTING_PROCESS),
		"stitch": total(lambda order: order["process_name"] in sewing),
		"packed": total(lambda order: cint(order.get("includes_packing"))),
	}


def get_pieces_per_box(lot_pieces, lot_boxes, packing_combos):
	"""The lots' single Packing Combo while their own pieces ÷ boxes agree with it within 10%, else that ratio; None with neither."""
	combos = {flt(combo) for combo in packing_combos if flt(combo)}
	combo = combos.pop() if len(combos) == 1 else None
	ratio = flt(lot_pieces) / flt(lot_boxes) if flt(lot_boxes) > 0 and flt(lot_pieces) > 0 else None
	if combo and (ratio is None or is_near(ratio, combo)):
		return combo
	return ratio


def is_near(value, reference):
	return bool(reference) and abs(flt(value) / flt(reference) - 1) <= MATCH_TOLERANCE


def get_ppo_pieces(boxes, pieces_per_box, lot_pieces):
	"""(pieces, unit) of a PPO: boxes × pieces per box, or the quantity itself when it already matches its lots' pieces.

	Some PPOs store pieces in their box quantity: the quantity is then within 10% of the lots' pieces and boxes × pieces
	per box is not. (None, "") without pieces per box.
	"""
	if not pieces_per_box:
		return None, ""
	as_boxes = flt(boxes) * pieces_per_box
	if pieces_per_box != 1 and is_near(boxes, lot_pieces) and not is_near(as_boxes, lot_pieces):
		return flt(boxes), "pieces"
	return as_boxes, "boxes"


def split_quantity(total, weights):
	"""`total` split over `weights` ({key: weight}) in proportion; equally when every weight is 0."""
	if not weights:
		return {}
	whole = sum(flt(weight) for weight in weights.values())
	if whole <= 0:
		return dict.fromkeys(weights, flt(total) / len(weights))
	return {key: flt(total) * flt(weight) / whole for key, weight in weights.items()}


def get_dispatch_multiplier(is_batch_tracked, pieces_per_box):
	"""Batch-tracked packing records dispatched pieces; older Finishing Plans record boxes."""
	return 1 if is_batch_tracked else flt(pieces_per_box)


def get_process_kind(process, orders, lot_item):
	if any(order["item"] != lot_item for order in orders):
		return "cloth"
	if process == CUTTING_PROCESS:
		return "cutting"
	if any(cint(order.get("includes_packing")) for order in orders):
		return "packing"
	return "item"


def get_status_reason(orders):
	if len(orders) == 1:
		return f"WO {orders[0]['status']}"
	done = sum(rules.order_status(order) == "done" for order in orders)
	return f"{done} of {len(orders)} WOs done"


def sort_by_first_dc(rows):
	return sorted(rows, key=lambda row: (row["first_dc"] is None, str(row["first_dc"] or "")))
