from collections import defaultdict
from functools import cached_property

import frappe
from frappe.utils import cint

from essdee_yrp.merch import lot_process_rules as rules
from essdee_yrp.planning.dashboard.lot_metrics import WORK_ORDER, LotMetrics
from essdee_yrp.planning.dashboard.processes import LotProcesses
from essdee_yrp.planning.dashboard.production_orders import OPEN_PPO_FILTERS, PPO, get_lots

NO_WORK_ORDER = "No Work Order"
STAGE_RANKS = {"Cutting": 0, "Cut stage": 1, "Stitching": 2, "Piece stage": 3, "Packing": 4}
DONE_STATUSES = {"Fully Received", "Partially Billed", "Fully Billed", "Close Request", "Closed"}
MOVING_STATUSES = {"Partially Delivered", "Fully Delivered", "Partially Received"}


def get_process_status_data():
	"""Process columns and per-lot cells for every open lot of the open PPOs (the Dashboard rows)."""
	production_orders = frappe.get_list(PPO, filters=OPEN_PPO_FILTERS, pluck="name", limit_page_length=0)
	status = LotProcessStatus(get_lots(production_orders))
	return {
		"processes": status.columns,
		"lots": {lot: status.get_cells(lot) for lot in status.lots},
	}


def get_order_tone(order):
	"""done, moving or idle; a closed Work Order is done whatever it received."""
	if cint(order["docstatus"]) == 0:
		return "idle"
	if order.get("open_status") == "Close" or order["status"] in DONE_STATUSES:
		return "done"
	return "moving" if order["status"] in MOVING_STATUSES else "idle"


def get_cell_status(orders):
	if not orders:
		return NO_WORK_ORDER
	if all(cint(order["docstatus"]) == 0 for order in orders):
		return "Draft"
	tones = {get_order_tone(order) for order in orders}
	if tones == {"done"}:
		return "Completed"
	return "Not Started" if tones == {"idle"} else "In Progress"


def get_cell(orders, steps):
	"""Combined status of one lot process over all its Work Orders, with the PPO Tracking step rows."""
	submitted = dict.fromkeys(order["process_name"] for order in orders if cint(order["docstatus"]) == 1)
	return {
		"status": get_cell_status(orders),
		"work_orders": len(orders),
		"drafts": sum(1 for order in orders if cint(order["docstatus"]) == 0),
		"steps": [steps[process] for process in submitted if process in steps],
	}


class LotProcessStatus:
	"""IPD processes of many lots (cloth IPD fabric processes, then garment steps) and their Work Order state."""

	def __init__(self, lots):
		self.lots = {row["name"]: row for row in lots}

	@cached_property
	def item_steps(self):
		"""{garment IPD: [(process, stage rank, position in stage)]} in IPD step order."""
		names = list({row.get("production_detail") for row in self.lots.values()} - {None, ""})
		if not names:
			return {}
		headers = frappe.get_all(
			"YRP Item Production Detail",
			filters={"name": ["in", names]},
			fields=["name", "cutting_process", "stiching_process", "packing_process", "stiching_in_stage"],
			limit_page_length=0,
		)
		processes = defaultdict(list)
		for row in frappe.get_all(
			"YRP IPD Process",
			filters={"parent": ["in", names], "parenttype": "YRP Item Production Detail"},
			fields=["parent", "process_name", "in_stage"],
			order_by="idx asc",
			limit_page_length=0,
		):
			processes[row["parent"]].append(row)
		return {
			ipd["name"]: get_ranked_steps(rules.item_steps(ipd, processes[ipd["name"]])) for ipd in headers
		}

	@cached_property
	def fabric_steps(self):
		"""{lot: [(fabric process, sequence)]} from the IPD Fabric Processes of the lot's cloth IPDs."""
		if not self.lots:
			return {}
		rows = frappe.db.sql(
			"""select distinct fd.parent, fp.fabric_process, fp.sequence
			from `tabSD YRP Lot Fabric Detail` fd
			join `tabSD YRP IPD Fabric Process` fp on fp.parent=fd.production_detail
			where fd.parenttype='SD YRP Lot' and fd.parent in %(names)s and ifnull(fp.fabric_process, '')<>''""",
			{"names": tuple(self.lots)},
		)
		result = defaultdict(list)
		for lot, process, sequence in rows:
			result[lot].append((process, cint(sequence)))
		return result

	@cached_property
	def orders(self):
		"""Draft and submitted production Work Orders of the lots."""
		if not self.lots:
			return []
		return frappe.get_list(
			WORK_ORDER,
			filters={
				"lot": ["in", list(self.lots)],
				"docstatus": ["<", 2],
				"is_rework": 0,
				"status": ["!=", "Cancelled"],
			},
			fields=["name", "lot", "process_name", "status", "docstatus", "open_status"],
			order_by="creation asc",
			limit_page_length=0,
		)

	@cached_property
	def groups(self):
		"""{group process: member processes} from YRP Process Details."""
		result = defaultdict(list)
		for row in frappe.get_all(
			"YRP Process Details",
			filters={"parenttype": "YRP Process"},
			fields=["parent", "process_name"],
			order_by="idx asc",
			limit_page_length=0,
		):
			result[row["parent"]].append(row["process_name"])
		return result

	@cached_property
	def steps(self):
		"""{lot: {Work Order process: PPO Tracking step row}} for lots with a submitted Work Order."""
		metrics = LotMetrics(list(self.lots.values()), sewing_processes=[])
		processes = LotProcesses(metrics)
		return {
			lot: {row["name"]: row for row in processes.get_processes(lot)} for lot in metrics.orders_by_lot
		}

	def get_lot_steps(self, lot):
		"""[(process, sort key)] of one lot: cloth IPD processes (key 0, ...), then garment IPD steps (key 1, ...)."""
		fabric = [(process, (0, sequence, 0)) for process, sequence in self.fabric_steps.get(lot, [])]
		ipd = self.lots[lot].get("production_detail")
		garment = [(process, (1, rank, position)) for process, rank, position in self.item_steps.get(ipd, [])]
		return fabric + garment

	@cached_property
	def columns(self):
		"""Every process in any lot's IPDs, fabric first, ordered by its earliest step position."""
		keys = {}
		for lot in self.lots:
			for process, key in self.get_lot_steps(lot):
				keys[process] = min(keys.get(process, key), key)
		ordered = sorted(keys, key=lambda process: (keys[process], process))
		return [
			{"name": process, "kind": "fabric" if keys[process][0] == 0 else "garment"} for process in ordered
		]

	@cached_property
	def orders_by_lot(self):
		result = defaultdict(lambda: defaultdict(list))
		for order in self.orders:
			result[order["lot"]][order["process_name"]].append(order)
		return result

	def get_process_orders(self, lot, process):
		"""Work Orders of the process itself and of group processes that cover it."""
		by_process = self.orders_by_lot.get(lot, {})
		covering = [group for group, members in self.groups.items() if process in members]
		return [order for name in [process, *covering] for order in by_process.get(name, [])]

	def get_cells(self, lot):
		"""{process: cell} for the processes in the lot's IPDs; others have no cell ('-')."""
		steps = self.steps.get(lot, {})
		processes = dict.fromkeys(process for process, _key in self.get_lot_steps(lot))
		return {process: get_cell(self.get_process_orders(lot, process), steps) for process in processes}


def get_ranked_steps(steps):
	"""[(process, stage rank, position within its stage)] from lot_process_rules.item_steps."""
	positions = defaultdict(int)
	ranked = []
	for step in steps:
		rank = STAGE_RANKS[step["stage"]]
		ranked.append((step["process"], rank, positions[rank]))
		positions[rank] += 1
	return ranked
