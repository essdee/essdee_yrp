"""Read-only review of an IPD shown before it is approved: header, key numbers, warnings, sections."""

import frappe
from frappe.utils import get_fullname

from essdee_yrp.merch.ipd.approval import sections
from essdee_yrp.merch.ipd.approval.piece_weight import (
	get_piece_weight,
	get_weight_span,
	get_weight_warnings,
	weight_groups,
)
from essdee_yrp.merch.ipd.checks import run_checks
from essdee_yrp.merch.ipd.draft import load_ipd
from essdee_yrp.merch.ipd.payload import build_payload

SECTION_LABELS = {
	"colours": "Main colours",
	"panels": "Panels",
	"weight": "Piece weight",
	"cloth_accessories": "Cloth accessory weight",
	"accessories": "Accessories",
	"embellishment": "Embellishment processes",
}


def get_attributes(values, context):
	known = {row["attribute"]: row.get("values") or [] for row in context.get("attributes") or []}
	is_set = bool(values.get("is_set_item"))
	return {
		"primary": values.get("primary_item_attribute") or "",
		"sizes": known.get(values.get("primary_item_attribute"), []),
		"packing": values.get("packing_attribute") or "Colour",
		"panel": values.get("stiching_attribute") or "Panel",
		"colours": [row["attribute_value"] for row in values.get("packing_attribute_details") or []],
		"is_set_item": is_set,
		"set_attribute": (values.get("set_item_attribute") or "") if is_set else "",
		"set_parts": known.get(values.get("set_item_attribute"), []) if is_set else [],
	}


def get_header(doc, payload):
	record, values = payload["record"], payload["values"]
	current = next((entry for entry in payload.get("used_by") or [] if entry["is_current"]), {})
	return {
		"name": doc.name,
		"item": record.get("item"),
		"item_name": record.get("item_name"),
		"item_group": frappe.db.get_value("Item", record.get("item"), "item_group")
		if record.get("item")
		else None,
		"version": record.get("version"),
		"status": record.get("approval_status"),
		"approved_by": record.get("approved_by_name") or record.get("approved_by") or "",
		"created_by": get_fullname(doc.owner),
		"created_on": str(doc.creation),
		"modified_by": get_fullname(doc.modified_by),
		"modified_on": str(doc.modified),
		"tech_pack_version": values.get("tech_pack_version") or "",
		"pattern_version": values.get("pattern_version") or "",
		"copied_from": record.get("copied_from") or "",
		"lots": current.get("lots") or [],
	}


def check_warnings(name):
	result = run_checks(name)
	return [
		{
			"level": level,
			"section": entry.get("section") or "review",
			"text": entry.get("message") or str(entry),
		}
		for key, level in (("problems", "danger"), ("warnings", "warning"))
		for entry in result.get(key) or []
	]


def build_summary(payload, header, checks=()):
	"""Summary from a workspace payload; kept free of database reads for tests."""
	values, context = payload["values"], payload["context"]
	attributes = get_attributes(values, context)
	panel_attribute = attributes["panel"]
	panel_wise = payload.get("panel_wise") if values.get("enable_panel_wise_consumption_matrix") else None
	groups, by_panel = weight_groups(values, panel_wise, panel_attribute, attributes["packing"])
	panels, panel_warnings = sections.get_panels(values, panel_attribute)
	panel_names = [panel["panel"] for panel in panels]
	colours, colour_warnings = sections.get_colours(values, panels, attributes)
	embellishment, embellishment_warnings = sections.get_embellishment(values, panel_names, panel_attribute)
	accessories, accessory_warnings = sections.get_accessories(values, context)
	cloth_accessories, cloth_accessory_warnings = sections.get_cloth_accessories(values)
	warnings = [
		*get_weight_warnings(groups, by_panel, panel_names, panel_attribute),
		*colour_warnings,
		*panel_warnings,
		*sections.cloth_warnings(values),
		*embellishment_warnings,
		*accessory_warnings,
		*cloth_accessory_warnings,
		*checks,
	]
	data = {
		"colours": colours,
		"panels": panels,
		"weight": get_piece_weight(values, attributes),
		"cloth_accessories": cloth_accessories,
		"accessories": accessories,
		"embellishment": embellishment,
	}
	return {
		"header": header,
		"attributes": attributes,
		"key_numbers": {
			"colours": len(colours["packing"]),
			"panels": len(panels),
			"pieces": sum(panel["qty"] or 0 for panel in panels),
			"piece_weight": get_weight_span(groups),
			"panel_wise": bool(values.get("enable_panel_wise_consumption_matrix")),
		},
		"warnings": warnings,
		"sections": [
			{"key": key, "label": label, "data": data[key]} for key, label in SECTION_LABELS.items()
		],
	}


def get_summary(name):
	doc = load_ipd(name, "read")
	payload = build_payload(doc)
	return build_summary(payload, get_header(doc, payload), check_warnings(name))
