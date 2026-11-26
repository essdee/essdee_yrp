import json

import frappe
from frappe.utils import flt
from yrp.stock.dimensions import get_dimension_fieldnames, get_valuation_dimensions
from yrp.stock.valuation import round_off_if_near_zero

NEGATIVE = "NEGATIVE"
UNTRACED = "UNTRACED"
MISMATCH_TOLERANCE = 0.01
SLE_FIELDS = (
	"name",
	"item",
	"warehouse",
	"lot",
	"received_type",
	"uom",
	"qty",
	"qty_after_transaction",
	"rate",
	"outgoing_rate",
	"valuation_adjustment_value",
	"stock_value_difference",
	"stock_queue",
	"voucher_type",
	"voucher_no",
	"voucher_detail_no",
	"paired_stock_ledger_entry",
	"valuation_is_stale",
	"posting_datetime",
	"creation",
)


class TracedFifo:
	"""FIFO replay that mirrors `FIFOValuation` but keeps one bin per source SLE and records every take."""

	def __init__(self, dimension_fields=("lot", "received_type")):
		self.queue = []
		self.dimension_fields = dimension_fields
		self.qty_by_dimensions = {}
		self.takes = {}
		self.sources = {}
		self.mismatches = {}
		self.resyncs = 0
		self.stored_queue = None

	def replay(self, rows):
		for row in rows:
			if self.stored_queue is not None and not same_queue(self.queue, self.stored_queue):
				self.resync(self.stored_queue)
			self.process(row)
			self.stored_queue = parse_queue(row.get("stock_queue"))
		return self

	def resync(self, stored):
		"""Adopt the ledger's stored queue, keeping the newest matching sources; unmatched stock is untraced."""
		self.resyncs += 1
		mine = [list(fifo_bin) for fifo_bin in self.queue]
		queue = []
		for qty, rate in reversed(stored):
			parts = []
			while qty > 1e-9 and mine and mine[-1][0] > 0 and abs(mine[-1][1] - rate) < 1e-9:
				take = min(qty, mine[-1][0])
				parts.append([take, rate, mine[-1][2]])
				mine[-1][0] -= take
				qty -= take
				if mine[-1][0] <= 1e-9:
					mine.pop()
			if qty > 1e-9 or qty < 0:
				parts.append([qty, rate, UNTRACED if qty > 0 else NEGATIVE])
			queue[:0] = reversed(parts)
		self.queue = queue

	def process(self, row):
		key = tuple(row.get(field) or "" for field in self.dimension_fields)
		current = self.qty_by_dimensions.get(key, 0.0)
		qty = flt(row.qty)
		if row.voucher_type == "YRP Stock Reconciliation":
			self.qty_by_dimensions[key] = self.reconcile(row, current)
			return
		if qty > 0:
			rate = flt(row.rate) + flt(row.valuation_adjustment_value) / qty
			self.sources[row.name] = {"qty": qty, "rate": rate}
			self.add_stock(qty, rate, row.name)
			self.qty_by_dimensions[key] = current + qty
			return
		consumed = self.remove_stock(abs(qty), flt(row.outgoing_rate))
		self.record_takes(row, consumed)
		self.qty_by_dimensions[key] = round_off_if_near_zero(current - abs(qty))

	def reconcile(self, row, current):
		target = flt(row.qty_after_transaction)
		rate = flt(row.rate)
		difference = target - current
		if difference > 0:
			self.sources[row.name] = {"qty": difference, "rate": rate}
			self.add_stock(difference, rate, row.name)
		elif difference < 0:
			self.record_takes(row, self.remove_stock(abs(difference), flt(row.outgoing_rate)))
		elif rate and target > 0 and abs(sum(flt(b[0]) for b in self.queue) - target) < 0.001:
			self.sources[row.name] = {"qty": target, "rate": rate}
			self.queue = [[target, rate, row.name]]
		return target

	def add_stock(self, qty, rate, source):
		if not self.queue:
			self.queue.append([0, 0, NEGATIVE])
		last = self.queue[-1]
		if last[0] > 0:
			self.queue.append([qty, rate, source])
			return
		net = last[0] + qty
		if net > 0:
			self.queue[-1] = [net, rate, source]
		else:
			last[0] = net

	def remove_stock(self, qty, outgoing_rate):
		consumed = []
		while qty:
			if not self.queue:
				self.queue.append([0, 0.0, NEGATIVE])
			fifo_bin = self.queue[0]
			if qty >= fifo_bin[0]:
				qty = round_off_if_near_zero(qty - fifo_bin[0])
				consumed.append(list(self.queue.pop(0)))
				if not self.queue and qty:
					rate = outgoing_rate or fifo_bin[1]
					self.queue.append([-qty, rate, NEGATIVE])
					consumed.append([qty, rate, NEGATIVE])
					break
			else:
				fifo_bin[0] = round_off_if_near_zero(fifo_bin[0] - qty)
				consumed.append([qty, fifo_bin[1], fifo_bin[2]])
				qty = 0
		return consumed

	def record_takes(self, row, consumed):
		merged = {}
		for qty, rate, source in consumed:
			if not qty:
				continue
			entry = merged.setdefault(source, [0.0, 0.0])
			entry[0] += qty
			entry[1] += qty * rate
		takes = [(source, qty, value) for source, (qty, value) in merged.items()]
		self.takes[row.name] = takes
		ledger_value = -flt(row.stock_value_difference)
		if abs(sum(take[2] for take in takes) - ledger_value) > MISMATCH_TOLERANCE:
			self.mismatches[row.name] = ledger_value - sum(take[2] for take in takes)


def parse_queue(value):
	if value in (None, ""):
		return None
	queue = json.loads(value) if isinstance(value, str) else value
	return [[flt(fifo_bin[0]), flt(fifo_bin[1])] for fifo_bin in queue or []]


def same_queue(queue, stored):
	"""Equal [qty, rate] state after merging adjacent same-rate bins, as the engine stores it."""
	merged = []
	for qty, rate, _source in queue:
		if merged and abs(merged[-1][1] - rate) < 1e-9:
			merged[-1][0] += qty
		else:
			merged.append([qty, rate])
	merged = [fifo_bin for fifo_bin in merged if abs(fifo_bin[0]) > 1e-9]
	stored = [fifo_bin for fifo_bin in stored if abs(fifo_bin[0]) > 1e-9]
	return len(merged) == len(stored) and all(
		abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6 for a, b in zip(merged, stored, strict=True)
	)


def get_bucket_rows(bucket):
	"""Active SLEs of one valuation bucket in engine replay order."""
	filters = {"item": bucket["item"], "warehouse": bucket["warehouse"], "is_cancelled": 0}
	for fieldname in get_valuation_dimensions():
		filters[fieldname] = bucket.get(fieldname) or ("is", "not set")
	fields = list(dict.fromkeys([*SLE_FIELDS, *get_dimension_fieldnames()]))
	return frappe.get_all(
		"YRP Stock Ledger Entry",
		filters=filters,
		fields=fields,
		order_by="posting_datetime asc, creation asc, name asc",
	)


def replay_bucket(bucket):
	rows = get_bucket_rows(bucket)
	return TracedFifo(tuple(get_dimension_fieldnames())).replay(rows), rows
