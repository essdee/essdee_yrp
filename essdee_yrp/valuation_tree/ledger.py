from collections import defaultdict

import frappe
from frappe.utils import flt
from yrp.stock.dimensions import get_valuation_dimensions

from essdee_yrp.valuation_tree.traced_fifo import SLE_FIELDS, replay_bucket

PI = "Purchase Invoice Rate Difference"
WO_CLOSE = "Work Order Excess Usage"
FINAL_ADJUSTMENT_STATUSES = ("Completed", "Reversed", "Draft")
SETTLED_ENTRY_STATUSES = ("Applied", "Terminal")


class LedgerReader:
	"""Cached, read-only access to the ledger rows the valuation tree walks."""

	def __init__(self):
		self.sles = {}
		self.buckets = {}
		self.link_totals = {}
		self.grn_deliverables = {}
		self.grn_rows = {}
		self.vouchers = {}
		self.items = {}
		self.work_orders = {}
		self.pending_by_target = self.get_pending_adjustments()

	def sle(self, name):
		if name not in self.sles:
			row = frappe.db.get_value("YRP Stock Ledger Entry", name, list(SLE_FIELDS), as_dict=True)
			if not row:
				frappe.throw(f"Stock Ledger Entry {name} not found")
			self.sles[name] = row
		return self.sles[name]

	def bucket_of(self, sle):
		return (sle.item, sle.warehouse, *(sle.get(field) or "" for field in get_valuation_dimensions()))

	def fifo(self, sle):
		"""Traced replay of the bucket that holds `sle`."""
		key = self.bucket_of(sle)
		if key not in self.buckets:
			bucket = {"item": sle.item, "warehouse": sle.warehouse}
			bucket.update({field: sle.get(field) for field in get_valuation_dimensions()})
			fifo, rows = replay_bucket(bucket)
			for row in rows:
				self.sles.setdefault(row.name, row)
			self.buckets[key] = fifo
		return self.buckets[key]

	def links_into(self, output_sle):
		return frappe.get_all(
			"YRP Stock Valuation Production Link",
			filters={"output_receipt_sle": output_sle, "active": 1},
			fields=["consumption_sle", "allocation_weight", "source_doctype", "source_name", "source_row"],
			order_by="creation asc, name asc",
		)

	def outputs_of(self, consumption_sle):
		return frappe.get_all(
			"YRP Stock Valuation Production Link",
			filters={"consumption_sle": consumption_sle, "active": 1},
			pluck="output_receipt_sle",
			order_by="output_receipt_sle",
		)

	def link_total(self, consumption_sle):
		if consumption_sle not in self.link_totals:
			self.link_totals[consumption_sle] = flt(
				frappe.db.sql(
					"""select sum(allocation_weight) from `tabYRP Stock Valuation Production Link`
					where consumption_sle = %s and active = 1""",
					consumption_sle,
				)[0][0]
			)
		return self.link_totals[consumption_sle]

	def deliverables(self, grn):
		if grn not in self.grn_deliverables:
			self.grn_deliverables[grn] = frappe.get_all(
				"SD YRP GRN Deliverable",
				filters={"parent": grn, "parenttype": "YRP Goods Received Note"},
				fields=[
					"name",
					"item_variant",
					"received_item_variant",
					"goods_received_note_item",
					"stock_qty",
					"stock_uom",
					"valuation_rate",
					"material_value",
					"consumption_sle",
					"output_receipt_sle",
				],
				order_by="idx asc",
			)
		return self.grn_deliverables[grn]

	def grn_items(self, grn):
		if grn not in self.grn_rows:
			rows = frappe.get_all(
				"YRP Goods Received Note Item",
				filters={"parent": grn, "parenttype": "YRP Goods Received Note"},
				fields=[
					"name",
					"item_variant",
					"stock_qty",
					"stock_uom",
					"rate",
					"amount",
					"freight_amount",
					"current_valuation_value",
				],
				order_by="idx asc",
			)
			self.grn_rows[grn] = {row.name: row for row in rows}
		return self.grn_rows[grn]

	def voucher(self, voucher_type, voucher_no):
		key = (voucher_type, voucher_no)
		if key not in self.vouchers:
			self.vouchers[key] = self.load_voucher(voucher_type, voucher_no)
		return self.vouchers[key]

	def load_voucher(self, voucher_type, voucher_no):
		if voucher_type == "YRP Goods Received Note":
			row = (
				frappe.db.get_value(
					voucher_type, voucher_no, ["against", "against_id", "supplier"], as_dict=True
				)
				or {}
			)
			process = (
				self.work_order(row.get("against_id")).get("process_name")
				if row.get("against") == "YRP Work Order"
				else ""
			)
			return frappe._dict(row, process=process)
		if voucher_type == "YRP Stock Entry":
			return frappe._dict(purpose=frappe.db.get_value(voucher_type, voucher_no, "purpose"))
		if voucher_type == "YRP Work Order":
			return frappe._dict(process=self.work_order(voucher_no).get("process_name"))
		return frappe._dict()

	def work_order(self, name):
		if not name:
			return {}
		if name not in self.work_orders:
			self.work_orders[name] = (
				frappe.db.get_value("YRP Work Order", name, ["process_name", "supplier"], as_dict=True) or {}
			)
		return self.work_orders[name]

	def item(self, name):
		if name not in self.items:
			row = (
				frappe.db.get_value("Item", name, ["item_name", "variant_of", "item_group"], as_dict=True)
				or {}
			)
			self.items[name] = frappe._dict(row, template=row.get("variant_of") or name)
		return self.items[name]

	def adjustments(self, sle_name):
		"""Applied adjustment value on a receipt split into own (Source) and inherited, by root adjustment type."""
		rows = frappe.db.sql(
			"""
			select e.entry_type, e.status, e.difference, e.source_sle, a.name as adjustment, a.adjustment_type,
				a.source_doctype, a.source_name, r.adjustment_type as reversed_type
			from `tabYRP Stock Valuation Propagation Entry` e
			join `tabYRP Stock Valuation Adjustment` a on a.name = e.adjustment
			left join `tabYRP Stock Valuation Adjustment` r on r.name = a.reversal_of
			where e.target_sle = %s
			""",
			sle_name,
			as_dict=True,
		)
		result = frappe._dict(
			own_pi=0.0,
			own_wo=0.0,
			inherited_pi=0.0,
			inherited_wo=0.0,
			own_docs=[],
			inherited_by_source=defaultdict(float),
		)
		for row in rows:
			if row.status not in SETTLED_ENTRY_STATUSES:
				continue
			kind = "pi" if (row.reversed_type or row.adjustment_type) == PI else "wo"
			scope = "own" if row.entry_type == "Source" else "inherited"
			result[f"{scope}_{kind}"] += flt(row.difference)
			if scope == "inherited":
				result.inherited_by_source[row.source_sle] += flt(row.difference)
			if scope == "own":
				result.own_docs.append(
					{
						"kind": kind,
						"adjustment": row.adjustment,
						"type": row.adjustment_type,
						"doctype": row.source_doctype,
						"name": row.source_name,
						"value": flt(row.difference),
					}
				)
		return result

	def get_pending_adjustments(self):
		"""Receipt SLE -> adjustments still queued, applying or failed."""
		pending = defaultdict(set)
		for target, adjustment in frappe.db.sql(
			"""select s.target_sle, a.name from `tabYRP Stock Valuation Adjustment Source` s
			join `tabYRP Stock Valuation Adjustment` a on a.name = s.parent
			where a.status not in %(final)s""",
			{"final": FINAL_ADJUSTMENT_STATUSES},
		):
			pending[target].add(adjustment)
		for target, adjustment in frappe.db.sql(
			"""select target_sle, adjustment from `tabYRP Stock Valuation Propagation Entry`
			where status not in %(settled)s""",
			{"settled": SETTLED_ENTRY_STATUSES},
		):
			pending[target].add(adjustment)
		return pending

	def pending_for(self, sle):
		names = set(self.pending_by_target.get(sle.name, ()))
		if sle.valuation_is_stale and not names:
			names.add("Stale valuation")
		return sorted(names)
