"""Submitted Work Orders of an IPD's lots, flagged when their process changed since the last approval."""

import json

import frappe

from essdee_yrp.ipd_ui import get_ipd_attribute_values
from essdee_yrp.merch.ipd.fields import DOCTYPE

STAGE_PREFIXES = (
	("stiching", "stiching_process"),
	("stitching", "stiching_process"),
	("cutting", "cutting_process"),
	("panel_wise", "cutting_process"),
	("cloth_accessory", "cutting_process"),
	("accessory_clothtype", "cutting_process"),
	("pack", "packing_process"),
)
ORDER_FIELDS = [
	"name",
	"process_name",
	"supplier",
	"supplier_name",
	"lot",
	"wo_date",
	"open_status",
	"is_rework",
	"planned_quantity",
]
QUANTITY_SQL = """
	select row.parent, row.item_variant as variant, row.qty, row.set_combination,
		colour.attribute_value as colour, size.attribute_value as size
	from `tab{table}` row
	join `tabItem` item on item.name = row.item_variant and item.variant_of = %(item)s
	left join `tabItem Variant Attribute` colour on colour.parent = row.item_variant
		and colour.parenttype = 'Item' and colour.attribute = %(colour)s
	left join `tabItem Variant Attribute` size on size.parent = row.item_variant
		and size.parenttype = 'Item' and size.attribute = %(size)s
	where row.parent in %(orders)s
"""


def ordered(values, preferred):
	known = [value for value in preferred if value in values]
	return known + [value for value in values if value not in known]


def set_colour(entry):
	combination = parse_json(entry.get("set_combination"))
	major = combination.get("major_colour") if isinstance(combination, dict) else None
	return major or entry["colour"]


def quantity_grid(rows, colours, sizes):
	"""Colour x size quantities; panels or set parts of one piece count once, under the set's major colour."""
	by_variant = {}
	for entry in rows:
		key = (set_colour(entry) or "", entry["size"] or "", entry["variant"])
		by_variant[key] = by_variant.get(key, 0) + (entry["qty"] or 0)
	cells = {}
	for (colour, size, _variant), qty in by_variant.items():
		cells[(colour, size)] = max(cells.get((colour, size), 0), qty)
	row_colours = ordered(list(dict.fromkeys(colour for colour, _size in cells)), colours)
	row_sizes = ordered(list(dict.fromkeys(size for _colour, size in cells)), sizes)
	return {
		"colours": row_colours,
		"sizes": row_sizes,
		"cells": [[cells.get((colour, size)) for size in row_sizes] for colour in row_colours],
		"total": sum(cells.values()),
	}


def parse_json(value):
	if isinstance(value, str):
		try:
			return json.loads(value)
		except ValueError:
			return value
	return value


def stage_field(fieldname):
	return next((field for prefix, field in STAGE_PREFIXES if fieldname.startswith(prefix)), None)


def embellishment_processes(old, new):
	old, new = parse_json(old) or {}, parse_json(new) or {}
	if not isinstance(old, dict) or not isinstance(new, dict):
		return []
	return [process for process in {**old, **new} if old.get(process) != new.get(process)]


def field_changes(entry, stages, labels):
	fieldname, old, new = entry[0], entry[1], entry[2]
	if parse_json(old) == parse_json(new):
		return []
	if fieldname == "emblishment_details_json":
		return [(process, "Embellishment panels changed") for process in embellishment_processes(old, new)]
	stage = stage_field(fieldname)
	label = labels.get(fieldname) or fieldname
	return [(stages[stage], f"{label} changed")] if stage and stages.get(stage) else []


def row_changes(version, bom_rows):
	found = []
	for action, verb in (("added", "added"), ("removed", "removed")):
		for table, data in version.get(action) or []:
			if table in ("item_bom", "ipd_processes") and data.get("process_name"):
				what = (
					f"BOM item {verb}: {data.get('item')}" if table == "item_bom" else f"Process row {verb}"
				)
				found.append((data["process_name"], what))
	for table, _idx, row_name, _fields in version.get("row_changed") or []:
		current = bom_rows.get(row_name) if table == "item_bom" else None
		if current and current.get("process_name"):
			found.append((current["process_name"], f"BOM item changed: {current.get('item')}"))
	return found


def is_approval(version):
	return any(
		entry[0] == "approval_status" and entry[2] == "Approved" for entry in version.get("changed") or []
	)


def get_changes(versions, stages, bom_rows, labels):
	"""Processes touched by the versions (newest first) saved after the latest approval."""
	since = []
	for version in versions:
		if is_approval(version):
			break
		since.append(version)
	else:
		return {"since_approval": False, "processes": []}
	processes = {}
	for version in reversed(since):
		found = row_changes(version, bom_rows)
		for entry in version.get("changed") or []:
			found.extend(field_changes(entry, stages, labels))
		for process, text in found:
			texts = processes.setdefault(process, [])
			if text not in texts:
				texts.append(text)
	return {
		"since_approval": True,
		"processes": [{"process": process, "changes": texts} for process, texts in processes.items()],
	}


def get_doc_changes(doc):
	versions = frappe.get_all(
		"Version",
		filters={"ref_doctype": DOCTYPE, "docname": doc.name},
		fields=["data"],
		order_by="creation desc",
		limit=300,
	)
	stages = {field: doc.get(field) for _prefix, field in STAGE_PREFIXES}
	bom_rows = {row.name: {"process_name": row.process_name, "item": row.item} for row in doc.get("item_bom")}
	labels = {field.fieldname: field.label for field in doc.meta.fields if field.label}
	return get_changes([parse_json(version.data) or {} for version in versions], stages, bom_rows, labels)


def get_orders(doc):
	lots = frappe.get_all("SD YRP Lot", filters={"production_detail": doc.name}, pluck="name")
	filters = {"docstatus": 1}
	or_filters = {"production_detail": doc.name, **({"lot": ["in", lots]} if lots else {})}
	return frappe.get_all(
		"YRP Work Order",
		filters=filters,
		or_filters=or_filters,
		fields=ORDER_FIELDS,
		order_by="wo_date asc, name asc",
	)


def get_quantity_rows(doc, names, table):
	if not names:
		return []
	params = {
		"item": doc.item,
		"colour": doc.packing_attribute,
		"size": doc.primary_item_attribute,
		"orders": tuple(names),
	}
	return frappe.db.sql(QUANTITY_SQL.format(table=table), params, as_dict=True)


def group_rows(rows):
	grouped = {}
	for entry in rows:
		grouped.setdefault(entry.parent, []).append(entry)
	return grouped


def get_work_orders(doc, colours=None, sizes=None):
	"""Submitted Work Orders with colour x size quantities and the processes changed since approval."""
	orders = get_orders(doc)
	names = [order.name for order in orders]
	received = group_rows(get_quantity_rows(doc, names, "YRP Work Order Receivables"))
	missing = [name for name in names if not any(entry.colour for entry in received.get(name) or [])]
	delivered = group_rows(get_quantity_rows(doc, missing, "YRP Work Order Deliverables"))
	colours = colours if colours is not None else get_ipd_attribute_values(doc, doc.packing_attribute)
	sizes = sizes if sizes is not None else get_ipd_attribute_values(doc, doc.primary_item_attribute)
	changes = get_doc_changes(doc)
	affected = {entry["process"] for entry in changes["processes"]}
	return {
		"orders": [
			{
				**order,
				"wo_date": str(order.wo_date or ""),
				"is_affected": order.process_name in affected,
				"grid": quantity_grid(
					delivered.get(order.name) or received.get(order.name) or [], colours, sizes
				),
			}
			for order in orders
		],
		"changes": changes,
		"colour_attribute": doc.packing_attribute or "Colour",
		"size_attribute": doc.primary_item_attribute or "Size",
	}
