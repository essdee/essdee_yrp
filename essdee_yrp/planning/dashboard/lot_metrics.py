from collections import defaultdict
from functools import cached_property

import frappe
from frappe.utils import cint, flt

from essdee_yrp.planning.dashboard import ladder

WORK_ORDER = "YRP Work Order"
WORK_ORDER_FIELDS = [
	"name",
	"lot",
	"item",
	"process_name",
	"includes_packing",
	"is_rework",
	"status",
	"docstatus",
	"supplier",
	"supplier_name",
]


def get_sewing_processes():
	setting = frappe.db.get_single_value("SD YRP MRP Settings", "finishing_inward_process")
	details = frappe.get_all("YRP Process Details", fields=["parent", "process_name"], limit_page_length=0)
	used = frappe.db.sql(
		"""select distinct process_name from `tabYRP Work Order`
		where docstatus=1 and ifnull(process_name, '')<>''""",
		pluck=True,
	)
	return ladder.get_sewing_processes(setting, details, used)


def sum_by(query, names):
	"""{key: value} from a two-column grouped query over `names`; empty when there are no names."""
	if not names:
		return {}
	return {key: flt(value) for key, value in frappe.db.sql(query, {"names": tuple(names)})}


class LotMetrics:
	"""Batched ladder facts, quantities and dispatch for many lots; `lots` are SD YRP Lot rows."""

	def __init__(self, lots, sewing_processes=None):
		self.lots = {row["name"]: row for row in lots}
		self.names = list(self.lots)
		self.sewing = set(get_sewing_processes() if sewing_processes is None else sewing_processes)

	@cached_property
	def orders(self):
		"""Submitted Work Orders of the lots (rework included; callers filter)."""
		if not self.names:
			return []
		return frappe.get_list(
			WORK_ORDER,
			filters={"lot": ["in", self.names], "docstatus": 1},
			fields=WORK_ORDER_FIELDS,
			order_by="creation asc",
			limit_page_length=0,
		)

	@cached_property
	def orders_by_lot(self):
		result = defaultdict(list)
		for order in self.orders:
			result[order["lot"]].append(order)
		return result

	def get_production_orders(self, lot):
		return [order for order in self.orders_by_lot[lot] if not cint(order["is_rework"])]

	@cached_property
	def item_totals(self):
		"""{work order: {planned, delivered, received}} from Calculated Items."""
		names = [order["name"] for order in self.orders]
		rows = (
			frappe.db.sql(
				"""select parent, sum(quantity), sum(delivered_quantity), sum(received_qty)
			from `tabYRP Work Order Calculated Item`
			where parenttype='YRP Work Order' and parent in %(names)s group by parent""",
				{"names": tuple(names)},
			)
			if names
			else []
		)
		return {
			parent: {"planned": flt(planned), "delivered": flt(delivered), "received": flt(received)}
			for parent, planned, delivered, received in rows
		}

	def get_order_total(self, order, key):
		return self.item_totals.get(order["name"], {}).get(key, 0.0)

	@cached_property
	def order_quantities(self):
		"""{lot: (planned, cut)} from Lot Order Details."""
		rows = (
			frappe.db.sql(
				"""select parent, ifnull(sum(quantity), 0), ifnull(sum(cut_qty), 0) from `tabSD YRP Lot Order Detail`
			where parenttype='SD YRP Lot' and parent in %(names)s group by parent""",
				{"names": tuple(self.names)},
			)
			if self.names
			else []
		)
		return {parent: (flt(planned), flt(cut)) for parent, planned, cut in rows}

	@cached_property
	def cutting_statuses(self):
		rows = (
			frappe.db.sql(
				"""select lot, cp_status from `tabSD YRP Cutting Plan`
			where docstatus=1 and ifnull(cp_status, '')<>'Cancelled' and lot in %(names)s""",
				{"names": tuple(self.names)},
			)
			if self.names
			else []
		)
		statuses = defaultdict(list)
		for lot, status in rows:
			statuses[lot].append(status)
		return {lot: ladder.get_best_cutting_status(values) for lot, values in statuses.items()}

	@cached_property
	def lay_sheets(self):
		return sum_by(
			"""select cp.lot, count(*) from `tabSD YRP Cutting LaySheet` ls
			join `tabSD YRP Cutting Plan` cp on cp.name=ls.cutting_plan
			where cp.lot in %(names)s and cp.docstatus=1 and ifnull(ls.status, '')<>'Cancelled'
			group by cp.lot""",
			self.names,
		)

	@cached_property
	def cutting_delivered(self):
		"""Cutting Work Orders with a submitted Delivery Challan."""
		names = [order["name"] for order in self.orders if order["process_name"] == ladder.CUTTING_PROCESS]
		if not names:
			return set()
		return set(
			frappe.db.sql(
				"""select distinct work_order from `tabYRP Delivery Challan`
			where docstatus=1 and work_order in %(names)s""",
				{"names": tuple(names)},
				pluck=True,
			)
		)

	@cached_property
	def fabric_steps(self):
		"""{lot: {fabric process: step}} from the IPD Fabric Processes of the lot's cloth IPDs."""
		rows = (
			frappe.db.sql(
				"""select distinct fd.parent, fp.parent, fp.sequence, fp.idx, fp.fabric_process
			from `tabSD YRP Lot Fabric Detail` fd
			join `tabSD YRP IPD Fabric Process` fp on fp.parent=fd.production_detail
			where fd.parenttype='SD YRP Lot' and fd.parent in %(names)s
			order by fp.parent, fp.sequence, fp.idx""",
				{"names": tuple(self.names)},
			)
			if self.names
			else []
		)
		routes = defaultdict(lambda: defaultdict(list))
		for lot, ipd, _sequence, _idx, process in rows:
			routes[lot][ipd].append(process)
		return {lot: ladder.get_fabric_steps(by_ipd.values()) for lot, by_ipd in routes.items()}

	@cached_property
	def finishing_plans(self):
		"""Readable Finishing Plans of the lots that have an IPD (get_ocr_details counts no others)."""
		with_ipd = [name for name, row in self.lots.items() if row.get("production_detail")]
		if not with_ipd:
			return []
		return frappe.get_list(
			"SD YRP Finishing Plan",
			filters={"lot": ["in", with_ipd]},
			fields=["name", "lot", "work_order", "pieces_per_box"],
			order_by="name asc",
			limit_page_length=0,
		)

	@cached_property
	def finishing_plans_by_lot(self):
		result = defaultdict(list)
		for plan in self.finishing_plans:
			result[plan["lot"]].append(plan["name"])
		return result

	def get_finishing_plans(self, lot):
		return self.finishing_plans_by_lot[lot]

	@cached_property
	def dispatch(self):
		"""{lot: dispatched pieces}, the batched `get_ocr_details(lot)["total_dispatch"]`."""
		plans = self.finishing_plans
		tracked = self.get_batch_tracked_orders([row["work_order"] for row in plans if row.get("work_order")])
		dispatched = sum_by(
			"""select parent, sum(dispatched) from `tabSD YRP Finishing Plan GRN Detail`
			where parenttype='SD YRP Finishing Plan' and parent in %(names)s group by parent""",
			[row["name"] for row in plans],
		)
		result = defaultdict(float)
		for plan in plans:
			multiplier = ladder.get_dispatch_multiplier(
				plan.get("work_order") in tracked, plan["pieces_per_box"]
			)
			result[plan["lot"]] += dispatched.get(plan["name"], 0) * multiplier
		return result

	def get_batch_tracked_orders(self, work_orders):
		if not work_orders:
			return set()
		return set(
			frappe.get_all(
				"YRP Goods Received Note",
				filters={
					"against": WORK_ORDER,
					"against_id": ["in", work_orders],
					"docstatus": 1,
					"is_return": 0,
					"packing_calculation_version": [">=", 1],
				},
				pluck="against_id",
				limit_page_length=0,
			)
		)

	def get_facts(self, lot):
		planned, cut = self.order_quantities.get(lot, (0.0, 0.0))
		orders = self.get_production_orders(lot)
		sewing = [order for order in orders if order["process_name"] in self.sewing]
		packing = [order for order in self.orders_by_lot[lot] if cint(order["includes_packing"])]
		cutting = [order["name"] for order in orders if order["process_name"] == ladder.CUTTING_PROCESS]
		fabric_process, fabric_step = ladder.get_fabric_process(orders, self.fabric_steps.get(lot, {}))
		return {
			"planned": planned,
			"cut": cut,
			"dispatch": self.dispatch.get(lot, 0.0),
			"pack_delivered": sum(self.get_order_total(order, "delivered") for order in packing),
			"sewing_delivered": sum(self.get_order_total(order, "delivered") for order in sewing),
			"sewing_received": sum(self.get_order_total(order, "received") for order in sewing),
			"cutting_status": self.cutting_statuses.get(lot, ""),
			"lay_sheets": self.lay_sheets.get(lot, 0),
			"has_work_order": bool(self.orders_by_lot[lot]),
			"has_cutting_plan": lot in self.cutting_statuses,
			"has_cutting_work_order": bool(cutting),
			"is_cutting_delivered": any(name in self.cutting_delivered for name in cutting),
			"fabric_process": fabric_process,
			"fabric_step": fabric_step,
		}

	def get_summary(self, lot):
		"""Status, quantities and dispatch of one lot as the Dashboard and PPO Tracking show them."""
		facts = self.get_facts(lot)
		orders = self.get_production_orders(lot)
		received = {order["name"]: self.get_order_total(order, "received") for order in orders}
		total = ladder.get_basis(facts["planned"], facts["cut"])
		status = ladder.get_lot_status(facts)
		return {
			"status": status,
			"status_rank": ladder.get_status_rank(status, facts["fabric_step"]),
			"planned": facts["planned"],
			"order_cut": facts["cut"],
			**ladder.get_lot_quantities(orders, received, self.sewing),
			"total": total,
			"dispatch": facts["dispatch"],
			"balance": total - facts["dispatch"],
		}
