from collections import OrderedDict

import frappe
from frappe.utils import flt
from yrp.yrp.doctype.yrp_item.yrp_item import get_parent_item

from essdee_yrp.essdee_yrp.doctype.sd_yrp_ipd_settings.sd_yrp_ipd_settings import (
	get_colour_attribute,
	get_dia_attribute,
)
from essdee_yrp.fabric_program import get_program_fabric_types
from essdee_yrp.fabric_reference import get_reference_allocations
from essdee_yrp.fabric_requirement import get_fabric_type
from essdee_yrp.panel_wise_consumption import natural_key
from essdee_yrp.print_helpers import get_work_order_correction_rows
from essdee_yrp.purchase_order_attribute_values import get_variant_attributes

MAIN_FABRIC = get_fabric_type("cloth")


def is_cloth_work_order(doc):
	process = doc.get("process_name")
	return bool(process and frappe.db.get_value("YRP Process", process, "is_cloth_process"))


def get_work_order_cloth_program(doc, table):
	"""A cloth Work Order's deliverables or receivables in the Lot's Build Cloth Program layout.

	Submitted correction rows print in their own tables after the Work Order's rows.
	"""
	correction_rows = get_work_order_correction_rows(doc, table)
	resolver = ClothRowResolver.for_lot(doc.get("lot"))
	return {
		"tables": build_cloth_tables(resolver.get_entries(doc.get(table))),
		"correction_tables": build_cloth_tables(resolver.get_entries(correction_rows)),
	}


class ClothRowResolver:
	"""Turns Work Order rows into Build Cloth Program entries: item, fabric type, Dia, Colour and qty.

	A row's fabric type comes from the Lot's cloth program routes it feeds (its reference
	variants, else its own variant), so folding fabric separates from the main fabric.
	"""

	def __init__(self, fabric_types):
		self.fabric_types = fabric_types or {}
		self.variants = {}

	@classmethod
	def for_lot(cls, lot):
		if not lot or not frappe.db.exists("SD YRP Lot", lot):
			return cls({})
		return cls(get_program_fabric_types(frappe.get_doc("SD YRP Lot", lot)))

	def get_variant(self, item_variant):
		"""(item, Dia, Colour) of an Item Variant."""
		if item_variant not in self.variants:
			attributes = get_variant_attributes(item_variant)
			self.variants[item_variant] = (
				get_parent_item(item_variant),
				attributes.get(get_dia_attribute()) or "",
				attributes.get(get_colour_attribute()) or "",
			)
		return self.variants[item_variant]

	def get_entries(self, rows):
		entries = []
		for row in rows or []:
			item, dia, colour = self.get_variant(row.get("item_variant"))
			shares = self.get_fabric_type_shares(row) if dia else {"": 1}
			for fabric_type, share in shares.items():
				entries.append(
					{
						"item": item,
						"uom": row.get("uom") or "",
						"fabric_type": fabric_type,
						"dia": dia,
						"colour": colour or "No Colour",
						"qty": flt(row.get("qty")) * share,
						"secondary_qty": flt(row.get("secondary_qty")) * share,
						"secondary_uom": row.get("secondary_uom") or "",
					}
				)
		return entries

	def get_fabric_type_shares(self, row):
		"""{fabric type: fraction of the row}, weighted by the row's reference quantities."""
		references = get_reference_allocations(row) or {row.get("item_variant"): 1}
		weights = {}
		for variant, qty in references.items():
			for fabric_type, fraction in self.get_route_fabric_types(variant).items():
				weights[fabric_type] = weights.get(fabric_type, 0) + flt(qty) * fraction
		total = sum(weights.values())
		if not total:
			return {MAIN_FABRIC: 1}
		return {fabric_type: weight / total for fabric_type, weight in weights.items() if weight}

	def get_route_fabric_types(self, item_variant):
		"""{fabric type: fraction} of the program route for ``item_variant``; unknown routes are Main Fabric."""
		item, dia, colour = self.get_variant(item_variant)
		types = self.fabric_types.get((item, dia, colour or None)) or self.get_dia_fabric_types(item, dia)
		if not types:
			return {MAIN_FABRIC: 1}
		ordered = sorted(types.items(), key=lambda pair: (pair[0] != MAIN_FABRIC, pair[0]))
		total = sum(flt(values["weight"]) for _, values in ordered)
		if not total:
			return {ordered[0][0]: 1}
		return {fabric_type: flt(values["weight"]) / total for fabric_type, values in ordered}

	def get_dia_fabric_types(self, item, dia):
		"""Fabric types of every colour's route at ``dia``: greige rows have no final colour."""
		types = {}
		for (route_item, route_dia, _colour), route_types in self.fabric_types.items():
			if (route_item, route_dia) != (item, dia):
				continue
			for fabric_type, values in route_types.items():
				weight = types.setdefault(fabric_type, {"weight": 0})
				weight["weight"] += flt(values["weight"])
		return types


def build_cloth_tables(entries):
	"""Build Cloth Program tables: one per item and UOM, Main Fabric first, Dia ascending, Colour columns."""
	grouped = OrderedDict()
	for entry in entries:
		grouped.setdefault((entry["item"], entry["uom"]), []).append(entry)
	return [build_cloth_table(item, uom, item_entries) for (item, uom), item_entries in grouped.items()]


def build_cloth_table(item, uom, entries):
	colours = sorted({entry["colour"] for entry in entries})
	groups = OrderedDict()
	for entry in sorted(
		entries,
		key=lambda row: (row["fabric_type"] != MAIN_FABRIC, row["fabric_type"], natural_key(row["dia"])),
	):
		group = groups.setdefault(
			entry["fabric_type"],
			{
				"fabric_type": entry["fabric_type"],
				"routes": OrderedDict(),
				"colour_totals": dict.fromkeys(colours, 0),
				"colour_secondary": {colour: {} for colour in colours},
			},
		)
		route = group["routes"].setdefault(
			entry["dia"],
			{
				"dia": entry["dia"],
				"quantities": dict.fromkeys(colours, 0),
				"total": 0,
				"secondary": {colour: {} for colour in colours},
				"secondary_total": {},
			},
		)
		route["quantities"][entry["colour"]] += entry["qty"]
		route["total"] += entry["qty"]
		group["colour_totals"][entry["colour"]] += entry["qty"]
		secondary = get_entry_secondary(entry)
		add_secondary(route["secondary"][entry["colour"]], secondary)
		add_secondary(route["secondary_total"], secondary)
		add_secondary(group["colour_secondary"][entry["colour"]], secondary)
	colour_secondary = {colour: {} for colour in colours}
	for group in groups.values():
		group["routes"] = [round_quantities(route) for route in group["routes"].values()]
		group["colour_totals"] = rounded(group["colour_totals"])
		group["total"] = flt(sum(group["colour_totals"].values()), 3)
		group["colour_secondary"] = round_secondary(group["colour_secondary"])
		group["secondary_total"] = sum_secondary(group["colour_secondary"].values())
		for colour in colours:
			add_secondary(colour_secondary[colour], group["colour_secondary"][colour])
	secondary_total = sum_secondary(colour_secondary.values())
	return {
		"item": item,
		"uom": uom,
		"colours": colours,
		"fabric_groups": list(groups.values()),
		"colour_totals": {
			colour: flt(sum(group["colour_totals"][colour] for group in groups.values()), 3)
			for colour in colours
		},
		"total": flt(sum(group["total"] for group in groups.values()), 3),
		"has_fabric_type": any(entry["fabric_type"] for entry in entries),
		"colour_secondary": round_secondary(colour_secondary),
		"secondary_total": secondary_total,
		"has_secondary": bool(secondary_total),
	}


def get_entry_secondary(entry):
	"""{Secondary UOM: qty} of an entry; empty when no Secondary Qty was entered."""
	if not entry.get("secondary_qty") or not entry.get("secondary_uom"):
		return {}
	return {entry["secondary_uom"]: entry["secondary_qty"]}


def add_secondary(target, quantities):
	for secondary_uom, qty in quantities.items():
		target[secondary_uom] = target.get(secondary_uom, 0) + qty


def sum_secondary(quantities_list):
	total = {}
	for quantities in quantities_list:
		add_secondary(total, quantities)
	return rounded(total)


def round_secondary(by_colour):
	return {colour: rounded(quantities) for colour, quantities in by_colour.items()}


def rounded(quantities):
	return {key: flt(value, 3) for key, value in quantities.items()}


def round_quantities(route):
	return {
		**route,
		"quantities": rounded(route["quantities"]),
		"total": flt(route["total"], 3),
		"secondary": round_secondary(route["secondary"]),
		"secondary_total": rounded(route["secondary_total"]),
	}
