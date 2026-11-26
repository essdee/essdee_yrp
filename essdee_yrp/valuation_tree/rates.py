from collections import defaultdict

import frappe
from frappe.utils import flt

from essdee_yrp.valuation_tree.graph import LEAF_STAGES
from essdee_yrp.valuation_tree.rate_notes import SectionNotes, unit_of

ADDS = ("process", "accessories", "pi", "wo_close", "unattributed")
TOTALS = ("value", "base", *ADDS)
OWN_COLUMNS = {
	"material": "base",
	"accessories": "base",
	"process": "process",
	"freight": "process",
	"pi": "pi",
	"wo_close": "wo_close",
	"pending": "unattributed",
	"unexplained": "unattributed",
	"inactive_link": "unattributed",
	"unattributed_leaf": "unattributed",
}
RESIDUAL_KINDS = {"reconciliation", "negative", "missing", "cycle", "untraced", "replay_difference"}
RECEIPT_KINDS = {"stock_entry", "transfer", *RESIDUAL_KINDS}
IDENTITY_TOLERANCE = 1e-6


class RateBuildUp:
	"""Per-process rate build-up of a valuation graph: Rate in + process + accessories + PI + WO close = Rate out."""

	def __init__(self, graph, reader, lot_item, root_names, pieces_per_box=0):
		"""`pieces_per_box` > 0 values the root rows per box of that many pieces."""
		self.graph = graph
		self.reader = reader
		self.nodes = graph.nodes
		self.prefix = f"{lot_item}-"
		self.root_names = list(root_names)
		self.pieces_per_box = flt(pieces_per_box)
		self.reachable = self.get_reachable()
		self.parents = self.get_parents()

	def get_reachable(self):
		seen, stack = set(), list(self.root_names)
		while stack:
			key = stack.pop()
			if key not in seen:
				seen.add(key)
				stack.extend(child["id"] for child in self.nodes[key]["children"])
		return seen

	def get_parents(self):
		parents = defaultdict(set)
		for key in self.reachable:
			for child in self.nodes[key]["children"]:
				parents[child["id"]].add((self.section_of(self.nodes[key]), child["link"] == "wo_close"))
		return parents

	def build(self):
		rows = self.get_rows()
		by_section = defaultdict(list)
		for (section, _item, _voucher), row in rows.items():
			by_section[section].append(row)
		root_section = self.section_of(self.nodes[self.root_names[0]])
		notes = SectionNotes(self.graph, self.short)
		sections = [
			self.get_section(title, by_section[title], title == root_section, notes)
			for title in self.get_order(by_section, root_section)
		]
		return {
			"sections": sections,
			"root_total": sum(row["total"] for row in sections[-1]["rows"]),
			"pieces_per_box": self.pieces_per_box,
			"has_unattributed": any(
				abs(row["unattributed"]) > 1e-9 for section in sections for row in section["rows"]
			),
		}

	def get_rows(self):
		rows = {}
		for key in sorted(self.reachable):
			node = self.nodes[key]
			if self.is_accessory_leaf(node):
				continue
			section = self.section_of(node)
			row_key = (section, self.short(node["item"]), node["voucher_no"])
			row = rows.setdefault(row_key, self.new_row(node, section))
			self.add_node(row, node)
		return rows

	def new_row(self, node, section):
		return {
			"section": section,
			"item": self.short(node["item"]),
			"voucher": node["voucher_no"],
			"voucher_type": node["voucher_type"],
			"against": node["against"],
			"against_id": node["against_id"],
			"kind": node["kind"],
			"uom": node["uom"],
			"posting": node["posting"],
			"qty": 0.0,
			"lines": 0,
			"nodes": [],
			"inputs": {},
			"accessory_inputs": {},
			"wo_inputs": {},
			"wo_issues": set(),
			"pi_docs": {},
			"to": set(),
			**dict.fromkeys(TOTALS, 0.0),
		}

	def add_node(self, row, node):
		row["qty"] += node["qty"]
		row["lines"] += 1
		row["nodes"].append(node["id"])
		row["value"] += node["value"]
		row["posting"] = min(row["posting"], node["posting"])
		row["to"] |= self.parents.get(node["id"], set())
		for doc in node["info"].get("own_docs", []):
			if doc["kind"] == "pi":
				row["pi_docs"][doc["name"]] = {
					"doctype": doc["doctype"],
					"name": doc["name"],
					"adjustment": doc["adjustment"],
				}
		for column, value in own_columns(node).items():
			row[column] += value
		for edge in node["children"]:
			self.add_edge(row, edge)

	def add_edge(self, row, edge):
		child = self.nodes[edge["id"]]
		qty, value = edge["fraction"] * child["qty"], edge["fraction"] * child["value"]
		if edge["link"] == "wo_close":
			row["wo_close"] += value
			row["wo_issues"].add(edge["issue"])
			add_line(row["wo_inputs"], self.line_key(child), self.line(child), qty, value)
		elif self.is_accessory_leaf(child):
			row["accessories"] += value
			add_line(row["accessory_inputs"], self.line_key(child), self.line(child), qty, value)
		else:
			self.add_input(row["inputs"], edge, child, qty, value)

	def add_input(self, inputs, edge, child, qty, value):
		"""A consumed item that differs from its origin (e.g. a loose piece moved in by a DC) is one line, its origins sources."""
		issue = self.reader.sle(edge["issue"])
		if issue.item == child["item"] or not edge.get("via"):
			add_line(inputs, self.line_key(child), self.line(child), qty, value)
			return
		hop = edge["via"][0]
		line = {
			"item": self.short(issue.item),
			"voucher": hop["voucher_no"],
			"voucher_type": hop["voucher_type"],
			"stage": "Transfer",
			"uom": issue.uom or child["uom"],
		}
		target = add_line(inputs, ("transfer", issue.item, hop["voucher_no"]), line, qty, value)
		add_line(target.setdefault("sources", {}), self.line_key(child), self.line(child), qty, value)

	def line_key(self, node):
		return (node["item"], node["voucher_no"], node["uom"])

	def line(self, node):
		accessory_stage = "Purchase" if node["kind"] == "purchase" else LEAF_STAGES.get(node["kind"])
		return {
			"item": self.short(node["item"]),
			"voucher": node["voucher_no"],
			"voucher_type": node["voucher_type"],
			"stage": accessory_stage if self.is_accessory_leaf(node) else self.section_of(node),
			"uom": node["uom"],
			"node": node["id"],
		}

	def is_accessory_leaf(self, node):
		return node["kind"] in ("purchase", "stock_entry") and self.graph.is_accessory(node["item"])

	def section_of(self, node):
		if node["kind"] == "purchase":
			return f"{purchase_group(node['item_group'])} purchase"
		return node["stage"]

	def short(self, item):
		return item[len(self.prefix) :] if item.startswith(self.prefix) else item

	def get_order(self, by_section, root_section):
		"""Process sections by first posting; receipt-only sections just before their first consumer; root last."""
		first = {name: min(row["posting"] for row in rows) for name, rows in by_section.items()}
		receipts = [
			name
			for name, rows in by_section.items()
			if name != root_section and all(row["kind"] in RECEIPT_KINDS for row in rows)
		]
		order = sorted(
			(name for name in by_section if name not in receipts and name != root_section),
			key=lambda name: first[name],
		)
		order.append(root_section)
		for name in sorted(receipts, key=lambda name: first[name]):
			consumers = {stage for row in by_section[name] for stage, _ in row["to"]}
			positions = [order.index(stage) for stage in consumers if stage in order]
			order.insert(min(positions) if positions else 0, name)
		return order

	def get_section(self, title, rows, is_root, notes):
		per_box = self.pieces_per_box if is_root else 0
		rows = sorted(rows, key=lambda row: (row["voucher"], row["item"]))
		out_rows = [self.row_out(row, per_box) for row in rows]
		section = {
			"id": title,
			"title": title,
			"kind": section_kind(rows),
			"is_root": is_root,
			"pieces_per_box": per_box,
			"rows": out_rows,
			"accessories": self.accessory_table(rows, per_box),
			"total": sum(row["total"] for row in out_rows),
		}
		section.update(notes.describe(section, rows))
		return section

	def row_out(self, row, per_box):
		units = row["qty"] / per_box if per_box else row["qty"]
		check_identity(row)
		rate_in = row["base"] + sum(line["value"] for line in row["inputs"].values())
		out = {
			"item": row["item"],
			"voucher": row["voucher"],
			"voucher_type": row["voucher_type"],
			"kind": row["kind"],
			"residual": LEAF_STAGES[row["kind"]] if row["kind"] in RESIDUAL_KINDS else "",
			"qty": units,
			"uom": "Box" if per_box else row["uom"],
			"unit": "box" if per_box else unit_of(row["uom"]),
			"uom_label": f"box ({per_box:g} pcs)" if per_box else unit_of(row["uom"]),
			"lines": row["lines"],
			"purchase_rate": per_unit(row["base"], units),
			"rate_in": per_unit(rate_in, units),
			**{column: per_unit(row[column], units) for column in ADDS},
			"rate_out": per_unit(row["value"], units),
			"total": row["value"],
			"inputs": lines_out(row["inputs"], units),
			"accessory_inputs": lines_out(row["accessory_inputs"], units),
			"wo_inputs": lines_out(row["wo_inputs"], units),
			"pi_docs": sorted(row["pi_docs"].values(), key=lambda doc: doc["name"]),
			"to": [{"stage": stage, "wo_close": wo} for stage, wo in sorted(row["to"])],
		}
		if per_box:
			out.update(
				pieces=row["qty"],
				pieces_per_box=per_box,
				rate_out_piece=row["value"] / row["qty"] if row["qty"] else 0,
			)
		return out

	def accessory_table(self, rows, per_box):
		used = {}
		for row in rows:
			units = row["qty"] / per_box if per_box else row["qty"]
			for key, line in row["accessory_inputs"].items():
				entry = used.setdefault(key, {**line, "qty": 0.0, "value": 0.0, "units": 0.0})
				entry["qty"] += line["qty"]
				entry["value"] += line["value"]
				entry["units"] += units
		return [self.accessory_out(entry) for _key, entry in sorted(used.items())]

	def accessory_out(self, entry):
		sources = [
			node
			for node in self.nodes.values()
			if node["item"] == self.nodes[entry["node"]]["item"]
			and node["voucher_no"] == entry["voucher"]
			and node["kind"] in ("purchase", "stock_entry")
		]
		qty = sum(node["qty"] for node in sources)
		value = sum(node["value"] for node in sources)
		pi = sum(node["own"].get("pi", 0) for node in sources)
		pi_doc = next(
			(doc for node in sources for doc in node["info"].get("own_docs", []) if doc["kind"] == "pi"), None
		)
		origin = self.nodes[entry["node"]]
		return {
			"item": entry["item"],
			"voucher": entry["voucher"],
			"voucher_type": entry["voucher_type"],
			"against": origin["against"],
			"against_id": origin["against_id"],
			"pi_doc": {"doctype": pi_doc["doctype"], "name": pi_doc["name"]} if pi_doc else None,
			"uom": entry["uom"],
			"unit": unit_of(entry["uom"]),
			"per_unit": entry["qty"] / entry["units"] if entry["units"] else 0,
			"rate": (value - pi) / qty if qty else 0,
			"pi": pi / qty if qty else 0,
			"added_per_unit": entry["value"] / entry["units"] if entry["units"] else 0,
			"qty": entry["qty"],
			"total": entry["value"],
		}


def own_columns(node):
	columns = defaultdict(float)
	for key, value in node["own"].items():
		if key == "rounding":
			column = "process" if node["info"].get("rounding_category", "process") == "process" else "base"
		elif key in OWN_COLUMNS:
			column = OWN_COLUMNS[key]
		else:
			frappe.throw(f"Valuation node {node['id']} has an unknown own value '{key}'")
		columns[column] += value
	return columns


def per_unit(value, units):
	return value / units if units else 0.0


def add_line(lines, key, line, qty, value):
	target = lines.setdefault(key, {**line, "qty": 0.0, "value": 0.0})
	target["qty"] += qty
	target["value"] += value
	return target


def lines_out(lines, units):
	out = []
	for line in sorted(lines.values(), key=lambda line: (line["item"], line["voucher"])):
		item = {key: value for key, value in line.items() if key not in ("qty", "value", "sources", "node")}
		item.update(
			unit=unit_of(line["uom"]),
			qty=line["qty"] / units if units else 0,
			amount=line["value"] / units if units else 0,
			rate=line["value"] / line["qty"] if line["qty"] else 0,
			total_qty=line["qty"],
			total=line["value"],
		)
		if line.get("sources"):
			item["sources"] = lines_out(line["sources"], units)
		out.append(item)
	return out


def check_identity(row):
	inputs = sum(line["value"] for line in row["inputs"].values())
	built = row["base"] + inputs + sum(row[column] for column in ADDS)
	if abs(built - row["value"]) > max(IDENTITY_TOLERANCE, abs(row["value"]) * 1e-9):
		frappe.throw(
			f"Rate build-up of {row['item']} on {row['voucher']} is {built} but its value is {row['value']}"
		)


def section_kind(rows):
	kinds = {row["kind"] for row in rows}
	if kinds == {"purchase"}:
		return "purchase"
	if kinds <= RECEIPT_KINDS:
		return "residual" if kinds <= RESIDUAL_KINDS else "receipt"
	return "process"


def purchase_group(item_group):
	group = item_group or "Material"
	for prefix in ("M_", "Purchase - "):
		group = group.removeprefix(prefix)
	return group
