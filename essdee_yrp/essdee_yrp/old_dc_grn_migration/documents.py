"""Create Work Orders, DCs and GRNs through the app's own APIs (Calculate popup, get_work_order_defaults)."""

from collections import defaultdict

import frappe
from frappe.utils import add_days, flt
from yrp.party_addresses import get_party_address
from yrp.stock.save_stock_items import group_items_for_ui

from essdee_yrp.api.work_order import (
	_variant_attrs,
	calculate_fabric_deliverables,
	get_fabric_deliverable_context,
)
from essdee_yrp.essdee_yrp.old_dc_grn_migration.plan import (
	KNITTING,
	allocate,
	allocate_rolls,
	move_to_offered_dias,
)

TAG = "Migrated from old DC/GRN: {number}"
FABRIC_STORE = "S-0005"
WO_SERIES = "YRP-WO-.YYYY.-"
QTY_TOLERANCE = 0.001
COLOUR, DIA = "Colour", "Dia"


class MigrationError(Exception):
	"""A lot step that cannot be done the way the app does it."""


def get_tag(number, cloth=None):
	return TAG.format(number=number) + (f" ({cloth})" if cloth else "")


def get_receipt_comments(grn):
	"""The GRN tag, then its remark (a derived GRN says where its quantity came from)."""
	return "\n".join(text for text in (get_tag(grn.number), grn.remark) if text)


def find_tagged(doctype, filters):
	return frappe.db.get_value(doctype, {**filters, "docstatus": 1}, "name")


def get_entries(qty_rows, line, *, knitting, greige_colour):
	"""Context qty rows that receive one plan line, with the line's kg spread over them."""
	if knitting:
		rows = [r for r in qty_rows if r.get("knit_colour") == line.colour and r.get("knit_dia") == line.dia]
		weights = [flt(r.get("prefill")) for r in rows]
	else:
		rows = [
			r
			for r in qty_rows
			if (r["out_attrs"].get(COLOUR), r["out_attrs"].get(DIA)) == (line.colour, line.dia)
		]
		if not rows:
			rows = [
				r
				for r in qty_rows
				if r["out_attrs"].get(DIA) == line.dia and r["out_attrs"].get(COLOUR) == greige_colour
			]
		weights = [flt(r.get("source_available", r.get("available"))) for r in rows]
	if not rows:
		return []
	return [(row, qty) for row, qty in zip(rows, allocate(line.kg, weights), strict=True) if qty > 0]


def make_entry(row, qty, manual_io):
	entry = {
		"key": row["key"],
		"matrix_key": row.get("matrix_key") or row["key"],
		"out_attrs": row["out_attrs"],
		"qty": qty,
	}
	for field in ("source_bucket_key", "source_mode"):
		if row.get(field):
			entry[field] = row[field]
	if row.get("knit_colour"):
		entry["colour"] = row["knit_colour"]
	if manual_io:
		entry["inputs"] = [
			{"key": i["key"], "qty": round(qty * flt(i["qty_per_output"]), 3)}
			for i in row.get("knitting_inputs") or []
		]
	return entry


class WorkOrderBuilder:
	"""One yrp Work Order for one WorkOrderPlan, built like the Desk Calculate popup."""

	def __init__(self, lot, plan, fabric_row, greige_colour):
		self.lot, self.plan, self.fabric_row, self.greige_colour = lot, plan, fabric_row, greige_colour
		self.notes = []
		self.knit_routes = set()

	def insert_draft(self, date):
		"""date = the posting date of the WO's DC (old DC date, or later when its source arrived later)."""
		plan = self.plan
		last_date = max([g.date for g in plan.grns] + [date])
		doc = frappe.new_doc("YRP Work Order")
		doc.update(
			{
				"naming_series": WO_SERIES,
				"process_name": plan.process,
				"lot": self.lot,
				"item": self.fabric_row.cloth_item,
				"production_detail": self.fabric_row.production_detail,
				"supplier": plan.supplier,
				"supplier_address": get_party_address(plan.supplier, preferred_type="Billing"),
				"delivery_location": FABRIC_STORE,
				"delivery_address": get_party_address(FABRIC_STORE, preferred_type="Billing"),
				"edit_wo_date": 1,
				"wo_date": date,
				"planned_start_date": date,
				"planned_end_date": last_date,
				"expected_delivery_date": max(last_date, str(add_days(date, 7))),
				"comments": get_tag(plan.dc.number, plan.cloth),
			}
		)
		doc.insert()
		return doc

	def calculate(self, doc):
		"""Try each earlier source process (nearest first) and use the first that receives every line."""
		context = get_fabric_deliverable_context(doc.name)
		options = [o["value"] for o in context.get("source_process_options") or []] or [None]
		errors = []
		for source in options:
			frappe.db.savepoint("old_dc_grn_calculate")
			try:
				if source:
					context = get_fabric_deliverable_context(doc.name, source_process=source)
				rows, missing = self.get_rows(context)
				if not missing:
					calculate_fabric_deliverables(doc.name, rows, source_process=source)
					self.knit_routes = self.get_knit_routes(context)
					return source
				errors.append(
					f"source {source or '-'}: no route for {missing} (IPD offers {self.get_offered(context)})"
				)
			except frappe.ValidationError as error:
				frappe.db.rollback(save_point="old_dc_grn_calculate")
				errors.append(f"source {source or '-'}: {error}")
		raise MigrationError(f"{self.plan.process} WO for {self.plan.dc.number}: " + "; ".join(errors))

	def get_knit_routes(self, context):
		"""(knit colour, knit Dia) pairs the cloth IPD can receive from Knitting."""
		row = next((r for r in context.get("rows") or [] if r["fabric_row"] == self.fabric_row.name), None)
		if not row or row["kind"] != "knitting":
			return set()
		return get_offered_knit_dias(row)

	def get_offered(self, context):
		row = next((r for r in context.get("rows") or [] if r["fabric_row"] == self.fabric_row.name), None)
		if not row:
			return "nothing for this cloth"
		if row["kind"] == "knitting":
			pairs = {f"knit {r.get('knit_colour')} {r.get('knit_dia')}" for r in row["qty_rows"]}
		else:
			pairs = {f"{r['out_attrs'].get(COLOUR)} {r['out_attrs'].get(DIA)}" for r in row["qty_rows"]}
		return ", ".join(sorted(pairs)[:12]) + (" ..." if len(pairs) > 12 else "")

	def get_rows(self, context):
		row = next((r for r in context.get("rows") or [] if r["fabric_row"] == self.fabric_row.name), None)
		if not row:
			return [], [f"{line.colour} {line.dia}" for line in self.plan.lines]
		knitting = row["kind"] == "knitting"
		if knitting:
			self.notes += move_to_offered_dias(self.plan, get_offered_knit_dias(row))
		entries, missing = [], []
		for line in self.plan.lines:
			matched = get_entries(row["qty_rows"], line, knitting=knitting, greige_colour=self.greige_colour)
			if not matched:
				missing.append(f"{line.old_colour}->{line.colour} {line.dia}")
			entries += [make_entry(qty_row, qty, row.get("manual_io")) for qty_row, qty in matched]
		entries = merge_entries(entries)
		if not knitting:
			self.cap_to_available(entries, row["qty_rows"])
		return [
			{"fabric_row": row["fabric_row"], "colour": None, "yarn_qty": None, "entries": entries}
		], missing

	def cap_to_available(self, entries, qty_rows):
		"""Send what the source GRNs actually hold: several output rows can share one source pool
		(Greige 26 Dia -> Maroon, Navy, Red), so each pool's entries are scaled down together."""
		rows = {(r["key"], r.get("source_bucket_key")): r for r in qty_rows}
		pools = defaultdict(list)
		for entry in entries:
			row = rows.get((entry["key"], entry.get("source_bucket_key")))
			if row and flt(row.get("source_available")) > 0:
				pools[(row.get("source_pool_key") or row["key"], flt(row["source_available"]))].append(entry)
		for (_pool, limit), pool_entries in pools.items():
			requested = round(sum(entry["qty"] for entry in pool_entries), 3)
			if requested <= limit + QTY_TOLERANCE:
				continue
			self.notes.append(
				f"{self.plan.dc.number}: {requested:g} kg capped to the {limit:g} kg received upstream"
			)
			shares = allocate(flt(limit, 3), [entry["qty"] for entry in pool_entries])
			for entry, share in zip(pool_entries, shares, strict=True):
				entry["qty"] = share


def get_offered_knit_dias(row):
	return {(r.get("knit_colour"), r.get("knit_dia")) for r in row["qty_rows"]}


def merge_entries(entries):
	merged = {}
	for entry in entries:
		key = (entry["key"], entry.get("source_bucket_key"))
		if key in merged:
			merged[key]["qty"] = round(merged[key]["qty"] + entry["qty"], 3)
			for current, extra in zip(
				merged[key].get("inputs") or [], entry.get("inputs") or [], strict=True
			):
				current["qty"] = round(current["qty"] + extra["qty"], 3)
		else:
			merged[key] = entry
	return list(merged.values())


def set_posting(doc, date, time):
	doc.edit_posting_date_and_time = 1
	doc.posting_date = date
	doc.posting_time = time


def make_delivery_challan(work_order, plan, date, time, quantities=None):
	"""Deliver every pending deliverable, as the DC form prefills it; quantities {item variant: qty} overrides that
	(an excess delivery against a fully delivered WO)."""
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import get_work_order_defaults

	defaults = get_work_order_defaults(work_order, posting_date=date, posting_time=time)
	for row in defaults["items"] if quantities else []:
		row["qty"] = row["delivered_quantity"] = quantities.get(row["item_variant"], 0)
	items = [row for row in defaults["items"] if flt(row.get("qty")) > 0]
	if not items:
		raise MigrationError(f"{work_order}: nothing pending to deliver for {plan.dc.number}")
	set_rolls(items, plan.lines, "qty")
	doc = frappe.new_doc("YRP Delivery Challan")
	doc.update(
		{
			k: v
			for k, v in defaults.items()
			if k not in ("items", "correction_items", "correction_item_details")
		}
	)
	doc.update(
		{
			"naming_series": "DC-.YYYY.-",
			"work_order": work_order,
			"from_address": get_party_address(defaults["from_location"], preferred_type="Billing"),
			"supplier_address": get_party_address(defaults["supplier"], preferred_type="Billing"),
			"comments": get_tag(plan.dc.number) + (" (excess yarn)" if quantities else ""),
			"supplier_document_no": plan.dc.number,
		}
	)
	doc.item_details = frappe.as_json(group_items_for_ui(items, "YRP Delivery Challan"))
	set_posting(doc, date, time)
	doc.insert()
	doc.submit()
	return doc


def set_rolls(items, lines, qty_field):
	"""Rolls go to the row with the same Colour and Dia; rows without one keep none."""
	rolls = defaultdict(int)
	for line in lines:
		rolls[(line.colour, line.dia)] += line.rolls
	for row in items:
		attrs = _variant_attrs(row["item_variant"])
		count = rolls.get((attrs.get(COLOUR), attrs.get(DIA)))
		if count and flt(row.get(qty_field)) > 0:
			row["secondary_qty"] = count


def make_goods_received_note(work_order, delivery_challan, grn, date, time, knit_routes, *, cap_to_pending):
	from yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note import get_work_order_defaults

	defaults = get_work_order_defaults(work_order, delivery_challan=delivery_challan)
	items, notes = fill_receipt_rows(defaults["items"], grn, knit_routes)
	if cap_to_pending:
		items, cap_notes = cap_receipt_to_pending(items, grn.number)
		notes += cap_notes
	if not items:
		return None, [*notes, f"{grn.number}: nothing pending on {work_order}, no GRN made"]
	doc = frappe.new_doc("YRP Goods Received Note")
	doc.update(
		{
			k: v
			for k, v in defaults.items()
			if k not in ("items", "correction_items", "correction_item_details")
		}
	)
	doc.update(
		{
			"naming_series": "YRP-GRN-.YYYY.-",
			"against": "YRP Work Order",
			"against_id": work_order,
			"delivery_challan": delivery_challan,
			"supplier_address": get_party_address(defaults["supplier"], preferred_type="Billing"),
			"delivery_address": get_party_address(defaults["delivery_location"], preferred_type="Billing"),
			"comments": get_receipt_comments(grn),
			"supplier_document_no": grn.number,
			"delivery_date": date,
		}
	)
	doc.item_details = frappe.as_json(group_items_for_ui(items, "YRP Goods Received Note"))
	set_posting(doc, date, time)
	doc.insert()
	doc.submit()
	return doc, notes


def is_booked_on_planned_dia(line, knit_routes):
	"""A GRN line in another Dia that the cloth IPD cannot receive as Actual Dia."""
	return line.dia != line.planned_dia and (line.colour, line.dia) not in knit_routes


def fill_receipt_rows(rows, grn, knit_routes):
	"""Book each GRN line on the receivable rows of its planned Colour/Dia (split by their pending kg when the
	WO's source buckets give several rows).

	Knitting keeps a different received Dia as the variant (Actual Dia) when the cloth IPD knits that Colour/Dia;
	otherwise (yrp computes an Actual Dia's yarn from the IPD's Knitting matrix and rejects a Dia it lacks) the line
	is booked on the planned Dia and noted. Returns (rows, notes).
	"""
	notes = []
	default_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
	for row in rows:
		row["quantity"] = 0
	by_attrs = {}
	for row in rows:
		if row.get("received_type") not in (None, default_type):
			continue
		attrs = _variant_attrs(row["item_variant"])
		by_attrs.setdefault((attrs.get(COLOUR), attrs.get(DIA)), []).append(row)
	extra = []
	for line in grn.lines:
		group = by_attrs.get((line.colour, line.planned_dia))
		if group is None:
			raise MigrationError(f"{grn.number}: no receivable for {line.colour} {line.planned_dia}")
		if is_booked_on_planned_dia(line, knit_routes):
			notes.append(
				f"{grn.number}: {line.kg:g} kg received as {line.dia} booked on planned {line.planned_dia}"
			)
		elif line.dia != line.planned_dia:
			extra.append(
				{
					**group[0],
					"item_variant": get_dia_variant(group[0]["item_variant"], line.dia),
					"quantity": line.kg,
					"secondary_qty": line.rolls,
				}
			)
			continue
		weights = [flt(row.get("pending_quantity")) for row in group]
		for row, kg, rolls in zip(
			group, allocate(line.kg, weights), allocate_rolls(line.rolls, weights), strict=True
		):
			row["quantity"] = round(flt(row["quantity"]) + kg, 3)
			row["secondary_qty"] = (row.get("secondary_qty") or 0) + rolls
	return [row for row in rows + extra if flt(row["quantity"]) > 0], notes


def cap_receipt_to_pending(rows, number):
	"""A process GRN consumes its input 1:1 from the supplier, so a gain over the delivered kg is booked only up to
	what is still pending there; the old excess is noted. Returns (rows, notes)."""
	notes = []
	for row in rows:
		pending = round(flt(row.get("pending_quantity")), 3)
		if flt(row["quantity"]) > pending + QTY_TOLERANCE:
			notes.append(
				f"{number}: {row['item_variant']} received {row['quantity']:g} kg, booked {pending:g} kg delivered"
			)
			row["quantity"] = pending
	return [row for row in rows if flt(row["quantity"]) > 0], notes


def get_dia_variant(item_variant, dia):
	from yrp.yrp.doctype.yrp_item.yrp_item import get_or_create_variant

	attrs = _variant_attrs(item_variant)
	attrs[DIA] = dia
	template = frappe.db.get_value("Item", item_variant, "variant_of")
	return get_or_create_variant(template, attrs)
