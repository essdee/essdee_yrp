"""Cloth programs (Build Cloth Programs), the cloth IPD Fabric Processes chain and garment IPD accessory Dias."""

import json

import frappe
from frappe.utils import flt

from essdee_yrp.api.cloth_program import (
	_item_variant_attributes,
	build_cloth_programs,
	get_cloth_program_context,
)
from essdee_yrp.api.work_order import _variant_attrs
from essdee_yrp.essdee_yrp.old_dc_grn_migration.plan import (
	COLOUR_STEPS,
	DYEING,
	IPD_ACCESSORY_DIAS,
	KNITTING,
)

COLOUR = "Colour"
STEP_GAP = 10


def get_fabric_rows(lot_doc):
	return {
		row.cloth_item: row
		for row in lot_doc.get("lot_fabric_details") or []
		if row.cloth_item and row.production_detail
	}


def get_knit_colours(plan, cloth):
	"""yrp colours the old Knitting Program DCs knitted for this cloth -> their old names."""
	colours = {}
	for work_order in plan.work_orders:
		if work_order.process == KNITTING and work_order.cloth == cloth:
			for line in work_order.lines:
				colours.setdefault(line.colour, []).append(line.old_colour)
	return colours


def find_yarn_colour(yarn_item, candidates):
	"""First candidate colour that already has a variant of the yarn template."""
	colours = {
		_variant_attrs(name).get(COLOUR)
		for name in frappe.get_all("Item", {"variant_of": yarn_item}, pluck="name")
	}
	return next((colour for colour in candidates if colour in colours), candidates[-1])


class ClothProgramSelection:
	"""Build Cloth Programs input for one cloth, from the old knitting colours and the lot's yarn stock colours."""

	def __init__(self, cloth, knit_colours, yarn_colour_map, greige_colour):
		self.cloth = cloth
		self.knit_colours = knit_colours
		self.yarn_colour_map = yarn_colour_map
		self.greige_colour = greige_colour

	def get_knit_colour(self, finished_colour):
		return finished_colour if finished_colour in self.knit_colours else self.greige_colour

	def get_yarn_colour(self, yarn_item, finished_colour):
		if COLOUR not in _item_variant_attributes(yarn_item):
			return None
		if self.get_knit_colour(finished_colour) == self.greige_colour:
			return self.greige_colour
		olds = self.knit_colours[finished_colour]
		candidates = [self.yarn_colour_map[old] for old in olds if old in self.yarn_colour_map] + [
			finished_colour
		]
		return find_yarn_colour(yarn_item, candidates)

	def build(self, defaults):
		cloth = self.cloth
		colours = list(
			dict.fromkeys(route["colour"] for route in cloth["required_routes"] if route["colour"])
		)
		recipes = [
			{
				"colour": colour,
				"yarn_item": yarn["yarn_item"],
				"yarn_colour": self.get_yarn_colour(yarn["yarn_item"], colour),
				"ratio": yarn["ratio"],
			}
			for colour in colours
			for yarn in cloth["item_yarns"]
		]
		routes = [
			{
				"finished_dia": route["dia"],
				"finished_colour": route["colour"],
				"knitting_output_dia": route["dia"],
				"knitting_output_colour": self.get_knit_colour(route["colour"]),
				"use_dyed_yarn": int(self.get_knit_colour(route["colour"]) != self.greige_colour),
			}
			for route in cloth["required_routes"]
			if route["dia"] and route["colour"]
		]
		profile = cloth.get("profile") or {}
		return {
			"cloth_item": cloth["cloth_item"],
			"production_detail": cloth.get("production_detail"),
			"colour_yarn_recipes": recipes,
			"fabric_routes": routes,
			"yarns": cloth["item_yarns"],
			"yarn_item": cloth["item_yarns"][0]["yarn_item"] if cloth["item_yarns"] else None,
			"knitting_process": profile.get("knitting_process") or defaults["knitting_process"],
			"dyeing_process": profile.get("dyeing_process") or defaults["dyeing_process"],
			"compacting_process": None,
			"cloth_per_kg_yarn": flt(profile.get("cloth_per_kg_yarn")) or defaults["cloth_per_kg_yarn"],
		}


def ensure_cloth_programs(lot_doc, plan, yarn_colour_map, greige_colour):
	"""Build the lot's cloth programs when a planned cloth has no Lot fabric row; returns the built CPD names."""
	needed = {work_order.cloth for work_order in plan.work_orders}
	if needed <= set(get_fabric_rows(lot_doc)):
		return []
	context = get_cloth_program_context(lot_doc.name)
	selections = [
		ClothProgramSelection(
			cloth, get_knit_colours(plan, cloth["cloth_item"]), yarn_colour_map, greige_colour
		).build(context["defaults"])
		for cloth in context["cloths"]
	]
	for selection in selections if plan.lot in COLOUR_STEPS else []:
		selection["dyeing_process"] = COLOUR_STEPS[plan.lot]["process"]
	result = build_cloth_programs(
		lot_doc.name, frappe.as_json(selections), excess_percentage=context["excess_percentage"]
	)
	return [row["cpd"] for row in result["programs"]]


def edit_ipd(ipd_name, reason, edit):
	"""Apply edit(ipd) and save; an Approved IPD is reverted first and re-approved after, through the app's own
	approval methods. Returns the approval log lines."""
	from essdee_yrp.ipd_ui import approve_ipd, revert_ipd_approval

	log = []
	was_approved = (
		frappe.db.get_value("YRP Item Production Detail", ipd_name, "approval_status") == "Approved"
	)
	if was_approved:
		revert_ipd_approval(ipd_name, reason=f"Old DC/GRN migration: {reason}")
		log.append(f"reverted approval of {ipd_name}")
	ipd = frappe.get_doc("YRP Item Production Detail", ipd_name)
	edit(ipd)
	ipd.save()
	if was_approved:
		approve_ipd(ipd_name)
		log.append(f"re-approved {ipd_name}")
	return log


def ensure_process_chain(ipd_name, processes, colour_process=None):
	"""Append missing processes to the cloth IPD's Fabric Processes chain as plain (identity) steps.

	colour_process (COLOUR_STEPS) takes over the Dyeing step, keeping its colour mappings.
	An IPD that already has every process is not touched. Returns (changes, approval log lines).
	"""
	ipd = frappe.get_doc("YRP Item Production Detail", ipd_name)
	existing = {row.fabric_process for row in ipd.get("fabric_processes") or []}
	replace_dyeing = bool(colour_process) and DYEING in existing and colour_process not in existing
	added = [process for process in processes if process not in existing and process != colour_process]
	changes = [f"{colour_process} in place of {DYEING}"] * replace_dyeing + added
	if not changes:
		return [], []

	def edit(ipd):
		if replace_dyeing:
			for row in ipd.fabric_processes:
				if row.fabric_process == DYEING:
					row.fabric_process = colour_process
			ipd.dyeing_process = colour_process
		sequence = max([row.sequence or 0 for row in ipd.fabric_processes] or [0])
		for process in added:
			sequence += STEP_GAP
			ipd.append(
				"fabric_processes",
				{
					"sequence": sequence,
					"fabric_process": process,
					"input_item": ipd.item,
					"output_item": ipd.item,
					"quantity_ratio": 1,
				},
			)

	return changes, edit_ipd(ipd_name, f"Fabric Processes {', '.join(changes)}", edit)


def get_process_chain(ipd_name):
	"""The cloth IPD's Fabric Processes in sequence order."""
	return frappe.get_all(
		"SD YRP IPD Fabric Process",
		filters={"parent": ipd_name, "parenttype": "YRP Item Production Detail"},
		order_by="sequence asc, idx asc",
		pluck="fabric_process",
	)


def ensure_accessory_dias(lot_doc):
	"""Apply the lot's IPD_ACCESSORY_DIAS to its garment IPD's accessory consumption rows.

	Fails when the IPD is not the lot's or is used by another lot, or has neither Dia. Returns (change, approval log)."""
	if lot_doc.name not in IPD_ACCESSORY_DIAS:
		return None, []
	ipd_name, old_dia, new_dia = IPD_ACCESSORY_DIAS[lot_doc.name]
	if lot_doc.production_detail != ipd_name:
		frappe.throw(f"lot {lot_doc.name} uses IPD {lot_doc.production_detail}, not {ipd_name}")
	others = frappe.get_all(
		"SD YRP Lot", {"production_detail": ipd_name, "name": ["!=", lot_doc.name]}, pluck="name"
	)
	if others:
		frappe.throw(f"IPD {ipd_name} is also used by lot(s) {', '.join(others)}; not changing its Dias")
	accessories = json.loads(
		frappe.db.get_value("YRP Item Production Detail", ipd_name, "cloth_accessory_json") or "{}"
	)
	dias = {row.get("Dia") for row in accessories.get("items") or []}
	if old_dia not in dias:
		if new_dia in dias:
			return None, []
		frappe.throw(
			f"IPD {ipd_name} has no accessory in {old_dia} (accessory Dias: {sorted(filter(None, dias))})"
		)
	for row in accessories["items"]:
		if row.get("Dia") == old_dia:
			row["Dia"] = new_dia
	change = f"{ipd_name}: accessory {old_dia} changed to {new_dia}"

	def edit(ipd):
		ipd.cloth_accessory_json = json.dumps(accessories)

	return change, edit_ipd(ipd_name, change, edit)
