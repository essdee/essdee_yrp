import frappe
from yrp.attribute_read_context import attribute_read_scope

from essdee_yrp.cutting.reports import serialize_multiccr_panel_groups
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import (
	build_ccr,
	fetch_cloth_details,
	remove_empty_rows,
)

SET_ITEM_VERSIONS = ("V2", "V3")


@frappe.whitelist()
def get_cutting_plan_ccr(cutting_plan):
	"""JSON-ready data of the "Essdee Cutting Plan CCR" print for the web CCR tab."""
	with attribute_read_scope():
		cutting_plan_doc = frappe.get_doc("SD YRP Cutting Plan", cutting_plan)
		cutting_plan_doc.check_permission("read")
		return build_cutting_plan_ccr(cutting_plan_doc)


def build_cutting_plan_ccr(cutting_plan_doc):
	ccr = build_ccr(cutting_plan_doc) or {}
	version = cutting_plan_doc.version
	return {
		"marker_groups": serialize_multiccr_panel_groups(cutting_plan_doc.name, ccr),
		"accessories": fetch_cloth_details(cutting_plan_doc.cutting_plan_accessory_details),
		"print_panels": list((ccr.get("print_panel_details") or {}).values()),
		"recuts": list((ccr.get("recut_details") or {}).values()),
		"cloth_groups": group_cloth_by_type(fetch_cloth_details(cutting_plan_doc.cutting_plan_cloth_details)),
		"completed": serialize_size_groups(cutting_plan_doc.completed_items_json, "completed", version),
		"excess": serialize_size_groups(cutting_plan_doc.incomplete_items_json, "incompleted", version),
	}


def group_cloth_by_type(cloth_rows):
	groups = {}
	for row in cloth_rows:
		groups.setdefault(row["cloth_type"], []).append(row)
	return [{"cloth_type": cloth_type, "rows": rows} for cloth_type, rows in groups.items()]


def serialize_size_groups(items_json, json_type, version):
	"""Rows with a non-zero quantity, labelled the way the CCR print labels them."""
	if not items_json:
		return []
	groups = []
	for group in remove_empty_rows(items_json, json_type) or []:
		is_set_item = bool(group.get("is_set_item"))
		groups.append(
			{
				"pack_attr": group.get("pack_attr"),
				"set_item_attr": group.get("set_item_attr") if is_set_item else None,
				"primary_values": group.get("primary_attribute_values") or [],
				"rows": [
					{
						"label": get_size_row_label(item, group.get("pack_attr"), version),
						"set_value": item["attributes"].get(group.get("set_item_attr"))
						if is_set_item
						else None,
						"values": item.get("values") or {},
					}
					for item in group.get("items") or []
				],
			}
		)
	return groups


def get_size_row_label(item, pack_attr, version):
	attributes = item.get("attributes") or {}
	label = attributes.get(pack_attr)
	is_minor_set_part = (
		version in SET_ITEM_VERSIONS
		and item.get("is_set_item")
		and attributes.get(item.get("set_attr")) != item.get("major_attr_value")
		and label
	)
	if is_minor_set_part:
		return f"{label} ({(item.get('item_keys') or {}).get('major_colour')})"
	return label
