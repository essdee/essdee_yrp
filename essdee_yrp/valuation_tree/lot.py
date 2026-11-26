from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.valuation_tree.graph import CATEGORIES, ValuationGraph
from essdee_yrp.valuation_tree.ledger import LedgerReader
from essdee_yrp.valuation_tree.rates import RateBuildUp

ACCESSORY_LAST = (
	"Purchased accessories",
	"Pending adjustment",
	"Negative stock",
	"Stock Reconciliation",
	"Untraced ledger stock",
	"Ledger replay difference",
	"Lineage missing",
	"Adjustment via inactive link",
	"Unexplained",
)
RESIDUAL_KINDS = ("negative", "missing", "reconciliation", "cycle", "untraced", "replay_difference")


class LotValuation:
	"""Valuation tree of a Lot: roots are its packing receipts, walked back to purchase leaves."""

	def __init__(self, lot):
		self.lot = frappe.get_doc("SD YRP Lot", lot)
		self.ipd = self.lot.production_detail
		self.reader = LedgerReader()
		self.accessory_templates = self.get_accessory_templates()
		self.graph = ValuationGraph(self.reader, self.is_accessory)

	def get_accessory_templates(self):
		if not self.ipd:
			return set()
		return set(
			frappe.get_all(
				"YRP Item BOM",
				filters={"parent": self.ipd, "parenttype": "YRP Item Production Detail"},
				pluck="item",
			)
		)

	def is_accessory(self, item):
		return self.reader.item(item).template in self.accessory_templates

	def get_root_receipts(self):
		"""Receipts of the Lot's packing GRNs; without packing yet, the most downstream stage received so far."""
		rows = frappe.db.sql(
			"""
			select s.name, s.voucher_no, s.posting_datetime, wo.process_name
			from `tabYRP Stock Ledger Entry` s
			join `tabYRP Goods Received Note` g on g.name = s.voucher_no and g.against = 'YRP Work Order'
			join `tabYRP Work Order` wo on wo.name = g.against_id
			where s.lot = %s and s.is_cancelled = 0 and s.qty > 0
				and s.voucher_type = 'YRP Goods Received Note' and s.paired_stock_ledger_entry is null
			order by s.posting_datetime, s.creation, s.name
			""",
			self.lot.name,
			as_dict=True,
		)
		packing = self.get_packing_processes()
		roots = [row for row in rows if row.process_name in packing]
		if roots or not rows:
			return roots, bool(roots)
		received = {row.process_name for row in rows}
		stage = next(
			(process for process in self.get_garment_processes() if process in received),
			rows[-1].process_name,
		)
		return [row for row in rows if row.process_name == stage], False

	def get_packing_processes(self):
		packing = (
			frappe.db.get_value("YRP Item Production Detail", self.ipd, "packing_process")
			if self.ipd
			else None
		)
		names = set(frappe.get_all("YRP Process", filters={"name": ["like", "%Packing%"]}, pluck="name"))
		return names | ({packing} if packing else set())

	def get_garment_processes(self):
		"""IPD garment processes, most downstream first: stitching, panel processes, cutting."""
		if not self.ipd:
			return []
		ipd = frappe.db.get_value(
			"YRP Item Production Detail", self.ipd, ["stiching_process", "cutting_process"], as_dict=True
		)
		panel = frappe.get_all(
			"YRP IPD Process",
			filters={"parent": self.ipd, "parenttype": "YRP Item Production Detail"},
			pluck="process_name",
			order_by="idx desc",
		)
		return [process for process in (ipd.stiching_process, *panel, ipd.cutting_process) if process]

	def build(self):
		roots, is_packing = self.get_root_receipts()
		if not roots:
			frappe.throw(_("Lot {0} has no production receipts to value yet.").format(self.lot.name))
		for root in roots:
			self.graph.node(root.name)
		groups = defaultdict(list)
		for root in roots:
			groups[root.voucher_no].append(root.name)
		pieces_per_box = flt(self.lot.get("packing_combo")) if is_packing else 0
		rates = RateBuildUp(
			self.graph, self.reader, self.lot.item, [root.name for root in roots], pieces_per_box
		)
		return {
			"lot": self.lot.name,
			"item": self.lot.item,
			"production_detail": self.ipd,
			"packing_combo": flt(self.lot.get("packing_combo")),
			"root_stage": roots[0].process_name,
			"root_is_packing": is_packing,
			"roots": [self.root_group(grn, names) for grn, names in groups.items()],
			"summary": self.summary([root.name for root in roots]),
			"rate_sections": rates.build(),
			"nodes": {key: serialize(node) for key, node in self.graph.nodes.items()},
		}

	def root_group(self, grn, names):
		nodes = [self.graph.nodes[name] for name in names]
		return {
			"grn": grn,
			"sles": names,
			"posting": nodes[0]["posting"],
			"qty": sum(node["qty"] for node in nodes),
			"value": sum(node["value"] for node in nodes),
			"summary": self.summary(names),
		}

	def summary(self, names):
		nodes = [self.graph.nodes[name] for name in names]
		categories = dict.fromkeys(CATEGORIES, 0.0)
		stages = defaultdict(float)
		for node in nodes:
			for key, value in node["categories"].items():
				categories[key] += value
			for key, value in self.graph.stages[node["id"]].items():
				stages[key] += value
		ledger = sum(node["value"] for node in nodes)
		qty = sum(node["qty"] for node in nodes)
		return {
			"qty": qty,
			"uom": nodes[0]["uom"],
			"ledger_value": ledger,
			"tree_value": sum(categories.values()),
			"categories": categories,
			"waterfall": self.waterfall(stages),
			"checks": self.checks(names),
		}

	def waterfall(self, stages):
		seen = self.graph.stage_first_seen

		def order(label):
			last = ACCESSORY_LAST.index(label) if label in ACCESSORY_LAST else -1
			suffix = next(
				(rank for rank, end in enumerate((" cost", " PI adj", " WO close")) if label.endswith(end)),
				-1,
			)
			return (last, seen.get(label) or "", suffix)

		return [
			{"stage": label, "value": value}
			for label, value in sorted(stages.items(), key=lambda pair: order(pair[0]))
			if abs(value) > 1e-9
		]

	def checks(self, names):
		"""Counts of residual kinds and unexplained value in the subtree."""
		counts = defaultdict(int)
		unexplained = 0.0
		seen = set()
		stack = list(names)
		while stack:
			key = stack.pop()
			if key in seen:
				continue
			seen.add(key)
			node = self.graph.nodes[key]
			counts["nodes"] += 1
			for kind in ("rounding", "pending", "unexplained", "inactive_link"):
				if node["own"].get(kind):
					counts[kind] += 1
			if node["kind"] in RESIDUAL_KINDS:
				counts[node["kind"]] += 1
			if node["pending"]:
				counts["pending_adjustments"] += 1
			unexplained += node["own"].get("unexplained", 0)
			stack.extend(child["id"] for child in node["children"])
		return {**counts, "unexplained_value": unexplained}


def serialize(node):
	keep = {key: node[key] for key in node if key not in ("own", "categories", "children", "info")}
	keep["own"] = {key: round(value, 6) for key, value in node["own"].items()}
	keep["categories"] = {key: round(value, 6) for key, value in node["categories"].items() if value}
	keep["children"] = [{**child, "fraction": round(child["fraction"], 12)} for child in node["children"]]
	keep["info"] = node["info"]
	keep["qty"] = round(node["qty"], 6)
	keep["value"] = round(node["value"], 6)
	return keep
