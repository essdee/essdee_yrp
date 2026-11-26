import re
from collections import defaultdict

import frappe
from frappe.utils import flt, fmt_money, formatdate

WO_CLOSE = "Work Order Excess Usage"
DOC_LABELS = {
	"YRP Work Order": "WO",
	"YRP Purchase Order": "PO",
	"YRP Delivery Challan": "DC",
	"YRP Goods Received Note": "GRN",
	"YRP Stock Entry": "Stock Entry",
	"YRP Stock Valuation Adjustment": "WO close",
}
AGAINST_DOCTYPES = {"Purchase Order": "YRP Purchase Order"}
UNITS = {"Kg": "kg", "Pieces": "pc", "Nos": "no.", "Box": "box"}


class SectionNotes:
	"""Documents, supplier and data-driven one-line notes of one rate build-up section."""

	def __init__(self, graph, short):
		self.graph = graph
		self.reader = graph.reader
		self.short = short

	def describe(self, section, rows):
		kind = section["kind"]
		if kind == "purchase":
			return self.purchase(section, rows)
		if kind in ("receipt", "residual"):
			return self.receipt(section, rows)
		return self.process(section, rows)

	def purchase(self, section, rows):
		suppliers = {self.reader.voucher(row["voucher_type"], row["voucher"]).get("supplier") for row in rows}
		orders = sorted(
			{row["against_id"] for row in rows if row["against"] == "Purchase Order" and row["against_id"]}
		)
		docs = [doc("YRP Purchase Order", name) for name in orders] + grn_docs(rows) + pi_docs(section)
		if len(rows) <= 3:
			notes = [purchase_note(row) for row in section["rows"]]
		else:
			notes = [
				"Rate in = purchase rate on each GRN; purchase invoice rate differences are added as PI adjustment."
			]
		return {"who": supplier_names(suppliers), "docs": docs, "notes": notes}

	def receipt(self, section, rows):
		docs = [doc(row["voucher_type"], row["voucher"]) for row in unique_vouchers(rows)]
		if section["kind"] == "residual":
			labels = ", ".join(sorted({row["residual"] for row in section["rows"]}))
			note = f"{labels}: the ledger holds this value but its lineage cannot be traced further, so it is shown as + Unattributed."
			return {"who": "", "docs": docs, "notes": [note]}
		entries = [row for row in unique_vouchers(rows) if row["voucher_type"] == "YRP Stock Entry"]
		purposes, notes = set(), []
		for entry in entries:
			info = frappe.db.get_value(
				"YRP Stock Entry", entry["voucher"], ["purpose", "against_id", "posting_date"], as_dict=True
			)
			purposes.add(info.purpose)
			items = ", ".join(row["item"] for row in section["rows"] if row["voucher"] == entry["voucher"])
			total = sum(row["total"] for row in section["rows"] if row["voucher"] == entry["voucher"])
			against = f" against {info.against_id}" if info.against_id else ""
			notes.append(
				f"{info.purpose} {short_doc(entry['voucher'])} ({dmy(info.posting_date)}){against}: {items}. Rate in = value on the stock entry ({inr(total)} in total)."
			)
		if len(entries) < len(unique_vouchers(rows)):
			notes.append(
				"Transfer receipts that could not be followed to their origin: value is the value they arrived with."
			)
		return {"who": ", ".join(sorted(purposes)), "docs": docs, "notes": notes}

	def process(self, section, rows):
		work_orders = sorted(
			{row["against_id"] for row in rows if row["against"] == "YRP Work Order" and row["against_id"]}
		)
		orders = [self.work_order(name) for name in work_orders]
		closes = [close for order in orders for close in order["closes"]]
		challans = self.challans(work_orders)
		docs = (
			[doc("YRP Work Order", name) for name in work_orders]
			+ [doc("YRP Stock Entry", name, "Transfer") for name in self.transfers(work_orders + challans)]
			+ [doc("YRP Delivery Challan", name) for name in challans]
			+ grn_docs(rows)
			+ pi_docs(section)
			+ [doc("YRP Stock Valuation Adjustment", close["name"]) for close in closes]
		)
		notes = [
			flow_note(section, rows),
			conversion_note(section),
			joined_note(section),
			returned_note(section),
			pi_note(section),
			self.wo_close_note(section, rows, orders),
			box_note(section),
		]
		who = ", ".join(sorted({order["supplier"] for order in orders if order["supplier"]}))
		return {"who": who, "docs": docs, "notes": [note for note in notes if note]}

	def work_order(self, name):
		fields = ["name", "supplier", "supplier_name", "status", "close_reason"]
		if frappe.get_meta("YRP Work Order").has_field("sd_close_reason"):
			fields.append("sd_close_reason")
		order = frappe.db.get_value("YRP Work Order", name, fields, as_dict=True)
		closes = frappe.get_all(
			"YRP Stock Valuation Adjustment",
			filters={
				"source_doctype": "YRP Work Order",
				"source_name": name,
				"docstatus": 1,
				"adjustment_type": WO_CLOSE,
				"status": "Completed",
			},
			fields=["name", "posting_date", "total_source_difference"],
			order_by="name",
		)
		return {
			"name": name,
			"supplier": order.supplier_name or order.supplier,
			"reason": order.get("sd_close_reason") or order.close_reason or "",
			"closes": closes,
		}

	def transfers(self, against):
		"""Stock entries moving stock for these work orders or challans (receipts excluded)."""
		if not against:
			return []
		return frappe.get_all(
			"YRP Stock Entry",
			filters={"against_id": ["in", against], "docstatus": 1, "purpose": ["!=", "Material Receipt"]},
			pluck="name",
			order_by="name",
		)

	def challans(self, work_orders):
		if not work_orders:
			return []
		return frappe.get_all(
			"YRP Delivery Challan",
			filters={"work_order": ["in", work_orders], "docstatus": 1},
			pluck="name",
			order_by="name",
		)

	def wo_close_note(self, section, rows, orders):
		absorbed = [row for row in section["rows"] if abs(row["wo_close"]) > 1e-9]
		if not absorbed:
			return ""
		parts = [self.close_part(order) for order in orders if order["closes"]]
		groups = [self.absorbed_group(issues, rows) for issues in self.issue_groups(rows)]
		parts.extend(groups)
		untouched = sorted({row["voucher"] for row in section["rows"]} - {row["voucher"] for row in absorbed})
		if untouched:
			parts.append(f"{', '.join(map(short_doc, untouched))} carries no WO close.")
		if not groups:
			total = sum(row["wo_close"] * row["qty"] for row in absorbed)
			parts.append(f"WO close {inr(total)} in total, posted on these receipts by the work order close.")
		return "WO close (unused inputs absorbed): " + " ".join(parts)

	def close_part(self, order):
		reason = f" for “{order['reason']}”" if order["reason"] else ""
		closes = ", ".join(
			f"{short_doc(close.name)} ({dmy(close.posting_date)})" for close in order["closes"]
		)
		return f"{short_doc(order['name'])} closed{reason}, {closes}."

	def issue_groups(self, rows):
		"""WO close issues grouped by the receipts that share them."""
		groups = defaultdict(list)
		for issue in sorted({issue for row in rows for issue in row["wo_issues"]}):
			groups[frozenset(self.reader.outputs_of(issue))].append(issue)
		return [(outputs, issues) for outputs, issues in groups.items()]

	def absorbed_group(self, group, rows):
		outputs, issues = group
		qty, value, items, uoms = 0.0, 0.0, [], set()
		for issue in issues:
			sle = self.reader.sle(issue)
			for edge in self.graph.edges_for_issue(sle, 1.0, "wo_close"):
				child = self.graph.nodes[edge["id"]]
				qty += edge["fraction"] * child["qty"]
				value += edge["fraction"] * child["value"]
				uoms.add(child["uom"])
			items.append(self.short(sle.item))
		received = [self.reader.sle(name) for name in outputs]
		count = sum(flt(sle.qty) for sle in received)
		in_valuation = sum(flt(sle.qty) for sle in received if any(sle.name in row["nodes"] for row in rows))
		unit = "/".join(sorted({unit_of(sle.uom) for sle in received}))
		share = f" ({fq(in_valuation)} in this valuation)" if abs(in_valuation - count) > 1e-9 else ""
		quantity = f" {fq(qty)} {unit_of(uoms.pop())}" if len(uoms) == 1 else ""
		per = value / count if count else 0
		return f"{item_list(items)}{quantity} = {inr(value)} ÷ {fq(count)} {unit}{share} = {inr(per)}/{unit}."


def purchase_note(row):
	note = (
		f"Rate in = purchase rate on {short_doc(row['voucher'])} ({inr(row['purchase_rate'])}/{row['unit']})."
	)
	if abs(row["pi"]) > 0.005:
		direction = "higher" if row["pi"] > 0 else "lower"
		note += f" The purchase invoice was {inr(abs(row['pi']))}/{row['unit']} {direction}, added as PI adjustment."
	return note


def flow_note(section, rows):
	out_qty, in_qty, stages = defaultdict(float), defaultdict(float), set()
	for row in rows:
		out_qty[row["uom"]] += row["qty"]
		for line in row["inputs"].values():
			in_qty[line["uom"]] += line["qty"]
			stages.add(line["stage"])
	if not in_qty:
		return ""
	vouchers = ", ".join(short_doc(voucher) for voucher in sorted({row["voucher"] for row in rows}))
	return (
		f"In: {qty_text(in_qty)} from {', '.join(sorted(stages))} → out: {qty_text(out_qty)} on {vouchers}."
	)


def conversion_note(section):
	"""Weight → count conversion (cutting): ₹/kg × kg per panel = ₹ per panel."""
	made = [
		row
		for row in section["rows"]
		if row["inputs"] and all(line["uom"] != row["uom"] for line in row["inputs"])
	]
	if not made or section["pieces_per_box"]:
		return ""
	examples = {}
	for row in made:
		weight = sum(line["qty"] for line in row["inputs"])
		rate = row["rate_in"] / weight if weight else 0
		key = (round(rate, 4), round(weight, 6), round(row["rate_in"], 4))
		examples.setdefault(key, (row, weight, rate))
	in_unit = made[0]["inputs"][0]["unit"]
	row, weight, rate = next(iter(examples.values()))
	formula = f"{inr(rate)}/{in_unit} × {fq(weight)} {in_unit} per {row['unit']} = {inr(row['rate_in'])} per {row['unit']}"
	if len(examples) == 1:
		inputs = {line["item"] for made_row in made for line in made_row["inputs"]}
		return f"All {len(made)} {made[0]['unit']} rows take the same pooled {in_unit} rate from {len(inputs)} input item(s): {formula} (Rate in)."
	return f"Rate in = the {in_unit} rate of the input it was made from × {in_unit} per {row['unit']}, e.g. {row['item']}: {formula}."


def joined_note(section):
	joined = [
		row
		for row in section["rows"]
		if row["inputs"]
		and all(line["uom"] == row["uom"] for line in row["inputs"])
		and len(row["inputs"]) > 1
		and not any(line.get("sources") for line in row["inputs"])
	]
	if not joined:
		return ""
	counts = sorted({round(sum(line["qty"] for line in row["inputs"]), 3) for row in joined})
	return f"Rate in of one {joined[0]['unit']} = the {' / '.join(fq(count) for count in counts)} input {joined[0]['inputs'][0]['unit']} it is made from."


def returned_note(section):
	returned = [
		row for row in section["rows"] if row["to"] and all(target["wo_close"] for target in row["to"])
	]
	if not returned:
		return ""
	quantities = defaultdict(float)
	for row in returned:
		quantities[row["unit"]] += row["qty"]
	destinations = ", ".join(sorted({target["stage"] for row in returned for target in row["to"]}))
	return f"{len(returned)} row(s) ({qty_text(quantities)}) are not processed further: they are returned and charged into {destinations} at work order close."


def pi_note(section):
	total = sum(row["pi"] * row["qty"] for row in section["rows"])
	if abs(total) < 0.005:
		return ""
	names = ", ".join(short_doc(item["name"]) for item in pi_docs(section))
	return f"PI adjustment {inr(total)} in total ({names})."


def box_note(section):
	per_box = section["pieces_per_box"]
	if not per_box:
		return ""
	transfers = sorted(
		{
			(line["item"], line["voucher"])
			for row in section["rows"]
			for line in row["inputs"]
			if line.get("sources")
		}
	)
	note = f"Valued per box of {fq(per_box)} pieces, so every rate is per box."
	if transfers:
		items = ", ".join(item for item, _voucher in transfers)
		vouchers = ", ".join(sorted({short_doc(voucher) for _item, voucher in transfers}))
		note += f" Pieces reach packing as {items} through {vouchers} and are packed first-in first-out; a box's Rate in = {fq(per_box)} × the loose piece's consumed rate."
	return note


def grn_docs(rows):
	return [doc(row["voucher_type"], row["voucher"]) for row in unique_vouchers(rows)]


def pi_docs(section):
	seen = {}
	for row in section["rows"]:
		for item in row["pi_docs"]:
			seen[item["name"]] = doc(item["doctype"], item["name"], "PI")
	for accessory in section["accessories"]:
		if accessory["pi_doc"]:
			seen[accessory["pi_doc"]["name"]] = doc(
				accessory["pi_doc"]["doctype"], accessory["pi_doc"]["name"], "PI"
			)
	return [seen[name] for name in sorted(seen)]


def unique_vouchers(rows):
	return list({row["voucher"]: row for row in sorted(rows, key=lambda row: row["voucher"])}.values())


def doc(doctype, name, label=None):
	doctype = AGAINST_DOCTYPES.get(doctype, doctype)
	return {"label": label or DOC_LABELS.get(doctype, doctype), "doctype": doctype, "name": name}


def supplier_names(suppliers):
	names = {
		frappe.db.get_value("Supplier", supplier, "supplier_name") or supplier
		for supplier in suppliers
		if supplier
	}
	return ", ".join(sorted(names))


def item_list(items):
	unique = list(dict.fromkeys(items))
	return ", ".join(unique) if len(unique) <= 2 else f"{unique[0]} +{len(unique) - 1} more"


def qty_text(quantities):
	return " + ".join(f"{fq(qty)} {unit_of(uom)}" for uom, qty in sorted(quantities.items()))


def unit_of(uom):
	return UNITS.get(uom, (uom or "").lower())


def inr(value):
	sign = "−" if value < -0.0049 else ""
	return f"{sign}₹{fmt_money(abs(value), 2, format='#,##,###.##')}"


def fq(value):
	return f"{flt(value):.4f}".rstrip("0").rstrip(".")


def dmy(value):
	return formatdate(value, "dd-mm-yyyy") if value else ""


def short_doc(name):
	return re.sub(r"-\d{4}-", "-", re.sub(r"^YRP-", "", name or ""))
