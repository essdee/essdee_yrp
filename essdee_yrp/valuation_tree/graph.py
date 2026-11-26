from collections import defaultdict

from frappe.utils import flt

from essdee_yrp.valuation_tree.traced_fifo import NEGATIVE, UNTRACED

CATEGORIES = ("material", "process", "accessories", "pi", "wo_close", "unattributed")
ROUNDING_TOLERANCE = 0.01
LEAF_STAGES = {
	"purchase": "Purchase",
	"stock_entry": "Stock Entry receipt",
	"reconciliation": "Stock Reconciliation",
	"negative": "Negative stock",
	"missing": "Lineage missing",
	"cycle": "Lineage missing",
	"untraced": "Untraced ledger stock",
	"replay_difference": "Ledger replay difference",
}
SYNTHETIC_SOURCES = {NEGATIVE: ("NEG", "negative"), UNTRACED: ("UNTRACED", "untraced")}


class ValuationGraph:
	"""Memoised valuation DAG: one node per receipt SLE at full quantity, children as fractions of other nodes."""

	def __init__(self, reader, is_accessory=lambda item: False):
		self.reader = reader
		self.is_accessory = is_accessory
		self.nodes = {}
		self.stages = {}
		self.stage_first_seen = {}
		self.resolved = {}
		self.building = set()

	def node(self, sle_name):
		if sle_name in self.nodes:
			return self.nodes[sle_name]
		if sle_name in self.building:
			return self.synthetic(f"CYCLE|{sle_name}", "cycle", self.reader.sle(sle_name), 0, 0)
		self.building.add(sle_name)
		try:
			sle = self.reader.sle(sle_name)
			links = self.reader.links_into(sle_name)
			node = self.production_node(sle, links) if links else self.leaf_node(sle)
		finally:
			self.building.discard(sle_name)
		self.nodes[sle_name] = node
		return node

	def base_node(self, sle, kind):
		item = self.reader.item(sle.item)
		voucher = self.reader.voucher(sle.voucher_type, sle.voucher_no)
		qty = flt(sle.qty)
		value = qty * flt(sle.rate) + flt(sle.valuation_adjustment_value)
		return {
			"id": sle.name,
			"kind": kind,
			"sle": sle.name,
			"item": sle.item,
			"item_name": item.get("item_name") or sle.item,
			"item_group": item.get("item_group") or "",
			"stage": voucher.get("process") or LEAF_STAGES.get(kind, sle.voucher_type),
			"voucher_type": sle.voucher_type,
			"voucher_no": sle.voucher_no,
			"against": voucher.get("against") or "",
			"against_id": voucher.get("against_id") or "",
			"warehouse": sle.warehouse,
			"lot": sle.lot,
			"received_type": sle.received_type,
			"uom": sle.uom,
			"posting": str(sle.posting_datetime or ""),
			"qty": qty,
			"value": value,
			"ledger_rate": flt(sle.rate),
			"own": defaultdict(float),
			"info": {},
			"children": [],
			"pending": self.reader.pending_for(sle),
		}

	def leaf_node(self, sle):
		if sle.paired_stock_ledger_entry and flt(sle.qty) > 0:
			return self.transfer_node(sle)
		kind = self.leaf_kind(sle)
		node = self.base_node(sle, kind)
		if kind in ("purchase", "stock_entry"):
			adjustments = self.reader.adjustments(sle.name)
			node["own"]["pi"] = adjustments.own_pi
			node["info"]["own_docs"] = adjustments.own_docs
			base = flt(sle.qty) * flt(sle.rate)
			self.settle_residual(
				node, node["value"] - base - adjustments.own_pi, base_category=self.leaf_category(sle)
			)
			node["own"][self.leaf_category(sle)] += base
		else:
			node["own"]["unattributed_leaf"] = node["value"]
		return self.finish(node)

	def leaf_kind(self, sle):
		voucher = self.reader.voucher(sle.voucher_type, sle.voucher_no)
		if sle.voucher_type == "YRP Goods Received Note" and voucher.get("against") == "Purchase Order":
			return "purchase"
		if sle.voucher_type == "YRP Stock Entry" and voucher.get("purpose") == "Material Receipt":
			return "stock_entry"
		if sle.voucher_type == "YRP Stock Reconciliation":
			return "reconciliation"
		return "missing"

	def leaf_category(self, sle):
		return "accessories" if self.is_accessory(sle.item) else "material"

	def transfer_node(self, sle):
		"""A transfer receipt with no production link: value follows its paired issue."""
		node = self.base_node(sle, "transfer")
		node["children"] = self.edges_for_issue(
			self.reader.sle(sle.paired_stock_ledger_entry), 1.0, "transfer"
		)
		self.settle_residual(node, node["value"] - self.children_value(node))
		return self.finish(node)

	def production_node(self, sle, links):
		node = self.base_node(sle, "production")
		edges = []
		for link in links:
			total = self.reader.link_total(link.consumption_sle) or flt(link.allocation_weight) or 1
			share = flt(link.allocation_weight) / total
			link_type = {"YRP Work Order": "wo_close", "SD YRP Item Conversion": "conversion"}.get(
				link.source_doctype, "production"
			)
			edges += self.edges_for_issue(self.reader.sle(link.consumption_sle), share, link_type)
		node["children"] = merge_edges(edges)
		adjustments = self.reader.adjustments(sle.name)
		has_close_links = any(edge["link"] == "wo_close" for edge in node["children"])
		node["info"].update(
			inherited_pi=adjustments.inherited_pi,
			inherited_wo=adjustments.inherited_wo,
			own_wo=adjustments.own_wo,
			own_docs=adjustments.own_docs,
			work_order=node["against_id"],
		)
		node["own"]["pi"] = adjustments.own_pi
		if not has_close_links:
			node["own"]["wo_close"] = adjustments.own_wo
		process, freight, derived = self.process_cost(sle, node, adjustments, has_close_links)
		node["own"]["process"] = process
		node["own"]["freight"] = freight
		node["info"]["process_cost_derived"] = derived
		residual = (
			node["value"]
			- self.children_value(node)
			- process
			- freight
			- adjustments.own_pi
			- node["own"]["wo_close"]
		)
		active = {link.consumption_sle for link in links}
		orphan = sum(
			value for source, value in adjustments.inherited_by_source.items() if source not in active
		)
		tolerance = rounding_tolerance(node["value"], len(node["children"]))
		if abs(orphan) > tolerance and abs(residual - orphan) <= tolerance:
			node["own"]["inactive_link"] = orphan
			node["info"]["inactive_link_sources"] = sorted(
				source for source in adjustments.inherited_by_source if source not in active
			)
			residual -= orphan
		self.settle_residual(node, residual)
		return self.finish(node)

	def process_cost(self, sle, node, adjustments, has_close_links):
		if sle.voucher_type != "YRP Goods Received Note":
			own_wo = 0 if has_close_links else adjustments.own_wo
			return node["value"] - self.children_value(node) - adjustments.own_pi - own_wo, 0.0, True
		deliverables = [
			row for row in self.reader.deliverables(sle.voucher_no) if row.output_receipt_sle == sle.name
		]
		rows = self.reader.grn_items(sle.voucher_no)
		row_names = {row.goods_received_note_item for row in deliverables} | {sle.voucher_detail_no}
		freight = sum(flt(rows[name].freight_amount) for name in row_names if name in rows)
		material = sum(flt(row.material_value) for row in deliverables)
		node["info"]["material_at_posting"] = material
		node["info"]["grn_rows"] = [
			{
				"row": name,
				"item": rows[name].item_variant,
				"qty": flt(rows[name].stock_qty),
				"rate": flt(rows[name].rate),
				"current_value": flt(rows[name].current_valuation_value),
			}
			for name in sorted(row_names)
			if name in rows
		]
		return flt(sle.qty) * flt(sle.rate) - material - freight, freight, False

	def edges_for_issue(self, issue, share, link_type):
		"""Children for `share` of an outgoing SLE, through its traced FIFO takes."""
		fifo = self.reader.fifo(issue)
		edges = []
		for source, qty, value in fifo.takes.get(issue.name, []):
			if source in SYNTHETIC_SOURCES:
				prefix, kind = SYNTHETIC_SOURCES[source]
				child = self.synthetic(f"{prefix}|{issue.name}", kind, issue, qty, value)
				edges.append(edge(child, share, link_type, issue))
				continue
			fraction = share * qty / fifo.sources[source]["qty"]
			for child_id, child_fraction, via in self.resolve(source, fifo):
				edges.append(
					{**edge(self.nodes[child_id], fraction * child_fraction, link_type, issue), "via": via}
				)
		if issue.name in fifo.mismatches:
			child = self.synthetic(
				f"REPLAY|{issue.name}", "replay_difference", issue, 0, fifo.mismatches[issue.name]
			)
			edges.append(edge(child, share, link_type, issue))
		if not fifo.takes.get(issue.name):
			child = self.synthetic(
				f"MISSING|{issue.name}",
				"missing",
				issue,
				abs(flt(issue.qty)),
				-flt(issue.stock_value_difference),
			)
			edges.append(edge(child, share, link_type, issue))
		return edges

	def resolve(self, source, fifo):
		"""(node id, fraction, transfer path) for the whole of an incoming source; transfers collapse into their origin."""
		if source in self.resolved:
			return self.resolved[source]
		sle = self.reader.sle(source)
		if sle.voucher_type == "YRP Stock Reconciliation":
			meta = fifo.sources[source]
			node = self.synthetic(
				f"RECO|{source}", "reconciliation", sle, meta["qty"], meta["qty"] * meta["rate"]
			)
			result = [(node["id"], 1.0, [])]
		elif (
			sle.paired_stock_ledger_entry
			and not self.reader.links_into(source)
			and source not in self.building
		):
			result = self.resolve_transfer(sle)
		else:
			result = [(self.node(source)["id"], 1.0, [])]
		self.resolved[source] = result
		return result

	def resolve_transfer(self, sle):
		issue = self.reader.sle(sle.paired_stock_ledger_entry)
		hop = {
			"voucher_type": sle.voucher_type,
			"voucher_no": sle.voucher_no,
			"from": issue.warehouse,
			"to": sle.warehouse,
		}
		self.building.add(sle.name)
		try:
			edges = self.edges_for_issue(issue, flt(sle.qty) / abs(flt(issue.qty) or 1), "transfer")
		finally:
			self.building.discard(sle.name)
		moved = sum(item["fraction"] * self.nodes[item["id"]]["value"] for item in edges)
		value = flt(sle.qty) * flt(sle.rate) + flt(sle.valuation_adjustment_value)
		if abs(moved - value) > rounding_tolerance(value, len(edges)):
			return [(self.node_without_collapse(sle)["id"], 1.0, [])]
		return [(item["id"], item["fraction"], [hop, *item.get("via", [])]) for item in edges]

	def node_without_collapse(self, sle):
		if sle.name not in self.nodes:
			self.nodes[sle.name] = self.transfer_node(sle)
		return self.nodes[sle.name]

	def synthetic(self, key, kind, sle, qty, value):
		if key in self.nodes:
			return self.nodes[key]
		node = self.base_node(sle, kind)
		node.update(id=key, qty=flt(qty), value=flt(value), pending=[])
		node["own"]["unattributed_leaf"] = node["value"]
		self.nodes[key] = self.finish(node)
		return node

	def children_value(self, node):
		return sum(child["fraction"] * self.nodes[child["id"]]["value"] for child in node["children"])

	def settle_residual(self, node, residual, base_category="process"):
		if abs(residual) <= rounding_tolerance(node["value"], len(node["children"])):
			node["own"]["rounding"] += residual
			node["info"]["rounding_category"] = base_category
		elif node["pending"]:
			node["own"]["pending"] += residual
		else:
			node["own"]["unexplained"] += residual

	def finish(self, node):
		"""Roll categories and stage contributions up from children; both are linear in the node's fraction."""
		own = node["own"]
		categories = dict.fromkeys(CATEGORIES, 0.0)
		stages = defaultdict(float)
		for child in node["children"]:
			child_node = self.nodes[child["id"]]
			if child["link"] == "wo_close":
				categories["wo_close"] += child["fraction"] * child_node["value"]
				stages[f"{node['stage']} WO close"] += child["fraction"] * child_node["value"]
				self.mark_seen(f"{node['stage']} WO close", node["posting"])
				continue
			for key, value in child_node["categories"].items():
				categories[key] += child["fraction"] * value
			for key, value in self.stages[child["id"]].items():
				stages[key] += child["fraction"] * value
		self.add_own(node, own, categories, stages)
		node["categories"] = categories
		node["own"] = {key: value for key, value in own.items() if value}
		self.stages[node["id"]] = dict(stages)
		return node

	def add_own(self, node, own, categories, stages):
		stage = node["stage"]
		leaf_label = "Purchased accessories" if own.get("accessories") else (node["item_group"] or "Material")
		rounding_category = node["info"].get("rounding_category", "process")
		contributions = (
			("material", own.get("material", 0), leaf_label),
			("accessories", own.get("accessories", 0), leaf_label),
			("process", own.get("process", 0) + own.get("freight", 0), f"{stage} cost"),
			(
				rounding_category,
				own.get("rounding", 0),
				leaf_label if rounding_category != "process" else f"{stage} cost",
			),
			("pi", own.get("pi", 0), f"{stage} PI adj"),
			("wo_close", own.get("wo_close", 0), f"{stage} WO close"),
			("unattributed", own.get("pending", 0), "Pending adjustment"),
			("unattributed", own.get("unexplained", 0), "Unexplained"),
			("unattributed", own.get("inactive_link", 0), "Adjustment via inactive link"),
			("unattributed", own.get("unattributed_leaf", 0), LEAF_STAGES.get(node["kind"], "Unattributed")),
		)
		for category, value, label in contributions:
			if not value:
				continue
			categories[category] += value
			stages[label] += value
			self.mark_seen(label, node["posting"])

	def mark_seen(self, label, posting):
		first = self.stage_first_seen.get(label)
		if posting and (not first or posting < first):
			self.stage_first_seen[label] = posting


def rounding_tolerance(value, terms=0):
	"""A paisa, plus half a stored third decimal per summed child value, or one part per million on large values."""
	return max(ROUNDING_TOLERANCE + 0.0005 * terms, abs(value) * 1e-6) + 1e-9


def edge(child, fraction, link_type, issue):
	return {"id": child["id"], "fraction": fraction, "link": link_type, "issue": issue.name, "via": []}


def merge_edges(edges):
	merged = {}
	for item in edges:
		key = (item["id"], item["link"])
		if key in merged:
			merged[key]["fraction"] += item["fraction"]
		else:
			merged[key] = dict(item)
	return list(merged.values())
