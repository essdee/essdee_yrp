"""One short timeline comment per IPD save: BOM items, packing and set colours, panels, accessories."""

from collections import Counter

import frappe
from frappe.utils import cstr, escape_html

from essdee_yrp.merch.ipd import fields as registry
from essdee_yrp.merch.ipd.payload import document_attribute_ids, prime_attribute_values

MAX_ENTRIES = 8


def on_update(doc, method=None):
	before = doc.get_doc_before_save()
	if not before or frappe.flags.in_migrate or frappe.flags.in_patch:
		return
	lines = get_change_lines(before, doc)
	if lines:
		add_change_comment(doc.name, lines)


def add_change_comment(name, lines):
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Comment",
			"comment_email": frappe.session.user,
			"reference_doctype": registry.DOCTYPE,
			"reference_name": name,
			"content": "<br>".join(escape_html(text) for text in lines),
		}
	).insert(ignore_permissions=True)


def get_change_lines(before, after) -> list[str]:
	prime_attribute_values(document_attribute_ids(before) | document_attribute_ids(after))
	packing_before = cstr(before.get("packing_attribute") or "value").lower()
	packing_after = cstr(after.get("packing_attribute") or "value").lower()
	lines = []
	for added_label, removed_label, rows, is_multiset in (
		(
			"Added BOM items:",
			"Removed BOM items:",
			lambda doc: table_rows(doc, "item_bom", "item", "process_name"),
			True,
		),
		(
			f"Packing {packing_after} added:",
			f"Packing {packing_before} removed:",
			lambda doc: table_rows(doc, "packing_attribute_details", "attribute_value"),
			False,
		),
		(
			"Set item colour added:",
			"Set item colour removed:",
			lambda doc: table_rows(
				doc, "set_item_combination_details", "attribute_value", "set_item_attribute_value"
			),
			False,
		),
		(
			"Stitching panel added:",
			"Stitching panel removed:",
			lambda doc: table_rows(
				doc, "stiching_item_details", "stiching_attribute_value", "set_item_attribute_value"
			),
			False,
		),
		("Cloth accessory added:", "Cloth accessory removed:", cloth_accessories, False),
	):
		before_rows, after_rows = rows(before), rows(after)
		if not is_multiset:
			before_rows, after_rows = list(dict.fromkeys(before_rows)), list(dict.fromkeys(after_rows))
		added, removed = get_row_changes(before_rows, after_rows)
		lines += entry_line(added_label, added) + entry_line(removed_label, removed)
	return lines


def get_row_changes(before, after) -> tuple[list[str], list[str]]:
	"""Multiset diff of (name, qualifier) rows. BOM rows repeat, while other kinds repeat per colour or combination and are compared distinct."""
	qualifiers = {}
	for name, qualifier in before + after:
		qualifiers.setdefault(name, set()).add(qualifier)
	return (
		row_labels(Counter(after) - Counter(before), qualifiers),
		row_labels(Counter(before) - Counter(after), qualifiers),
	)


def row_labels(counts, qualifiers) -> list[str]:
	labels = []
	for (name, qualifier), count in counts.items():
		label = f"{name} ({qualifier})" if qualifier and len(qualifiers[name]) > 1 else name
		labels.append(f"{label} ×{count}" if count > 1 else label)
	return labels


def entry_line(label, values) -> list[str]:
	if not values:
		return []
	extra = len(values) - MAX_ENTRIES
	return [f"{label} {', '.join(values[:MAX_ENTRIES])}" + (f", +{extra} more" if extra > 0 else "")]


def table_rows(doc, table, fieldname, qualifier_field=None) -> list[tuple[str, str]]:
	"""Rows as (name, qualifier); the qualifier, such as process or set item, disambiguates repeated names."""
	rows = (
		(
			get_display_value(row.get(fieldname)),
			get_display_value(row.get(qualifier_field)) if qualifier_field else "",
		)
		for row in doc.get(table) or []
	)
	return [row for row in rows if row[0]]


def get_display_value(raw) -> str:
	"""Attribute value for an id, or the raw id when its master is missing, so logging never fails a save."""
	if isinstance(raw, str) and raw.startswith("IAV-"):
		prime_attribute_values({raw})
		cached = frappe.local.attribute_link_values.get(raw)
		raw = cached.attribute_value if cached else raw
	return cstr(raw).strip()


def cloth_accessories(doc) -> list[tuple[str, str]]:
	data = registry.json_value(doc.get("cloth_accessory_json"))
	items = (data.get("items") or []) if isinstance(data, dict) else []
	names = (cstr(item.get("Accessory")).strip() for item in items if isinstance(item, dict))
	return [(name, "") for name in names if name]
