from collections import defaultdict
from functools import cached_property

import frappe
from frappe.utils import cint, flt

from essdee_yrp.finishing.alternative_transfers import get_alternative_transfers
from essdee_yrp.planning.dashboard import ladder
from essdee_yrp.purchase_order_approval import get_approval_item_groups

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
	def fabric_routes(self):
		"""{lot: [process list per cloth IPD]} from the IPD Fabric Processes of the lot's cloth IPDs."""
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
		return {lot: list(by_ipd.values()) for lot, by_ipd in routes.items()}

	@cached_property
	def fabric_steps(self):
		"""{lot: {fabric process: step}} over the lot's cloth routes."""
		return {lot: ladder.get_fabric_steps(routes) for lot, routes in self.fabric_routes.items()}

	@cached_property
	def purchase_lines(self):
		"""{lot: [(purchase order, uom, ordered, received)]} of submitted non-Development POs in the MRP Settings Approval Item Groups; folding lots skipped."""
		if not self.names:
			return {}
		rows = frappe.db.sql(
			"""select pi.lot, pi.parent, pi.uom,
			sum(pi.qty - ifnull(pi.cancelled_quantity, 0)), sum(ifnull(pi.received_qty, 0))
			from `tabPurchase Order Item` pi
			join `tabPurchase Order` po on po.name=pi.parent
			join `tabSD YRP Lot` lot on lot.name=pi.lot
			join `tabItem` item on item.name=pi.item_code
			left join `tabItem` template on template.name=item.variant_of
			where pi.parenttype='Purchase Order' and pi.lot in %(names)s and po.docstatus=1
			and ifnull(po.is_development, 0)=0 and ifnull(lot.is_folding_lot, 0)=0
			and (item.item_group in %(groups)s or template.item_group in %(groups)s)
			group by pi.lot, pi.parent, pi.uom
			order by pi.parent, pi.uom""",
			{"names": tuple(self.names), "groups": tuple(sorted(get_approval_item_groups()))},
		)
		result = defaultdict(list)
		for lot, order, uom, ordered, received in rows:
			result[lot].append((order, uom or "", flt(ordered), flt(received)))
		return result

	@cached_property
	def purchase_totals(self):
		"""{lot: (ordered, received)} over the lot's purchase lines, all units together."""
		return {
			lot: (sum(line[2] for line in lines), sum(line[3] for line in lines))
			for lot, lines in self.purchase_lines.items()
		}

	def get_purchase_summary(self, lot):
		"""Ordered and received per unit and the PO names of the lot's purchase lines; None without such a PO."""
		lines = self.purchase_lines.get(lot)
		if not lines:
			return None
		units = defaultdict(lambda: [0.0, 0.0])
		for _order, uom, ordered, received in lines:
			units[uom][0] += ordered
			units[uom][1] += received
		return {
			"units": [
				{"uom": uom, "ordered": flt(ordered, 3), "received": flt(received, 3)}
				for uom, (ordered, received) in sorted(units.items())
			],
			"purchase_orders": sorted({line[0] for line in lines}),
		}

	def get_purchase_status(self, lot):
		return ladder.get_purchase_status(*self.purchase_totals.get(lot, (0.0, 0.0)))

	@cached_property
	def fabric_deliveries(self):
		"""{lot: {process: delivered qty}} of production Work Order deliverables, for lots with Work Orders still on PO."""
		names = [
			name
			for name in self.names
			if self.orders_by_lot[name] and self.get_purchase_status(name) == ladder.PO_CREATED
		]
		if not names:
			return {}
		rows = frappe.db.sql(
			"""select wo.lot, wo.process_name, sum(d.qty - ifnull(d.pending_quantity, 0))
			from `tabYRP Work Order Deliverables` d
			join `tabYRP Work Order` wo on wo.name=d.parent
			where d.parenttype='YRP Work Order' and wo.docstatus=1 and ifnull(wo.is_rework, 0)=0
			and wo.lot in %(names)s
			group by wo.lot, wo.process_name""",
			{"names": tuple(names)},
		)
		result = defaultdict(dict)
		for lot, process, delivered in rows:
			result[lot][process] = flt(delivered)
		return result

	def get_moved_quantity(self, lot):
		"""PO quantity delivered into the first process of the lot's cloth routes."""
		first = {route[0] for route in self.fabric_routes.get(lot, []) if route}
		return sum(qty for process, qty in self.fabric_deliveries.get(lot, {}).items() if process in first)

	def get_purchase_split(self, lot, status, basis):
		"""PO Created share of a lot with Work Orders still in a fabric stage; None when nothing is left on PO."""
		if not self.orders_by_lot[lot]:
			return None
		ordered, _received = self.purchase_totals.get(lot, (0.0, 0.0))
		pieces = ladder.get_po_created_pieces(
			status, self.get_purchase_status(lot), basis, ordered, self.get_moved_quantity(lot)
		)
		if pieces <= 0:
			return None
		rank = ladder.get_status_rank(ladder.PO_CREATED, 0)
		return {"status": ladder.PO_CREATED, "status_rank": rank, "pieces": flt(pieces, 3)}

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

	@cached_property
	def alternatives(self):
		"""{lot: [alternative lot rows]} of the pieces each lot moved to alternative lots."""
		return get_alternative_transfers(self.names)

	def get_alternative_quantity(self, lot):
		return sum(row["quantity"] for row in self.alternatives.get(lot, []))

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
			"to_alternative": self.get_alternative_quantity(lot),
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
			"purchase_status": self.get_purchase_status(lot),
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
			"to_alternative": facts["to_alternative"],
			"alternatives": self.alternatives.get(lot, []),
			"balance": total - facts["dispatch"] - facts["to_alternative"],
			"purchase_split": self.get_purchase_split(lot, status, total),
		}
