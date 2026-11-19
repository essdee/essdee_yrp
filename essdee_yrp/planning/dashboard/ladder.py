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
STATUS_ORDER = [NO_WORK_ORDER, *LADDER]
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
DISPATCHED_SHARE = 0.9
SEWN_SHARE = 0.9


def get_basis(planned, cut):
	"""Lot pieces the ladder measures against: cut pieces once cut, else planned pieces."""
	return flt(cut) or flt(planned)


def get_balance(planned, cut, dispatch):
	return get_basis(planned, cut) - flt(dispatch)


def get_best_cutting_status(statuses):
	return max(statuses, key=lambda status: CUTTING_PLAN_RANK.get(status, 0)) if statuses else ""


def get_lot_status(facts):
	"""First matching rung, top (Dispatched) to bottom (Fabric not received); a fabric process name sits below Waiting for cutting."""
	if not facts["has_work_order"] and not facts["has_cutting_plan"]:
		return NO_WORK_ORDER
	basis = get_basis(facts["planned"], facts["cut"])
	dispatch = flt(facts["dispatch"])
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


def get_lot_quantities(orders, received_by_order, sewing):
	"""Cut, Stitching and Packed pieces of one lot; each Work Order counts once per figure."""
	unique = {order["name"]: order for order in orders}.values()

	def total(matches):
		return sum(flt(received_by_order.get(order["name"])) for order in unique if matches(order))

	return {
		"cut": total(lambda order: order["process_name"] == CUTTING_PROCESS),
		"stitch": total(lambda order: order["process_name"] in sewing),
		"packed": total(lambda order: cint(order.get("includes_packing"))),
	}


def get_ppo_pieces(boxes, packing_combos):
	"""PPO pieces = boxes × the single pieces per box of its lots; None means boxes only."""
	combos = {flt(combo) for combo in packing_combos if flt(combo)}
	return flt(boxes) * combos.pop() if len(combos) == 1 else None


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
