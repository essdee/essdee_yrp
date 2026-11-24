"""Change Item: point untouched accessory deliverables at the variants the current IPD Item BOM calculates.

Ported from production_api's Work Order "Change Item". Only the variant changes; the stored
quantity is retained, and rows already moved by a DC/GRN are never touched.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import escape_html, flt
from yrp.attribute_links import value as attribute_value
from yrp.utils import update_if_string_instance

from essdee_yrp.work_order_actions import (
	_expected_accessories,
	_open_submitted_work_order,
	_processes,
	_row_eligibility,
)

DELIVERABLES_DOCTYPE = "YRP Work Order Deliverables"


def format_attributes(attrs: dict) -> str:
	return ", ".join(f"{name}: {value}" for name, value in sorted((attrs or {}).items()))


def get_variant_identity(item_variant: str) -> tuple[str, dict]:
	variant = frappe.get_cached_doc("Item", item_variant)
	attrs = {row.attribute: attribute_value(row.attribute_value) for row in variant.get("attributes") or []}
	return (variant.variant_of or variant.name), attrs


def _attrs_key(row) -> tuple:
	return tuple(sorted((row.get("attrs") or {}).items()))


def get_row_pairs(old_rows: list[dict], new_rows: list[dict]) -> dict | None:
	"""Map each old row to one new row: one variant to one variant, else by identical attributes."""
	if len({row["item_variant"] for row in old_rows}) == 1 and len(new_rows) == 1:
		return {row["row_name"]: new_rows[0] for row in old_rows}
	new_by_attrs = defaultdict(list)
	for row in new_rows:
		new_by_attrs[_attrs_key(row)].append(row)
	pairs = {}
	for row in old_rows:
		matches = new_by_attrs.get(_attrs_key(row)) or []
		if len(matches) != 1:
			return None
		pairs[row["row_name"]] = matches[0]
	return pairs


def _change(old: dict, new: dict | None, action: str, reason: str | None) -> dict:
	return {
		"row_name": old["row_name"],
		"old_variant": old["item_variant"],
		"old_attributes": format_attributes(old.get("attrs")),
		"old_qty": flt(old["qty"], 3),
		"old_uom": old["uom"],
		"new_variant": (new or {}).get("item_variant", ""),
		"new_attributes": format_attributes((new or {}).get("attrs")),
		"new_qty": flt(old["qty"], 3),
		"new_uom": old["uom"],
		"calculated_qty": flt((new or {}).get("qty"), 3),
		"calculated_uom": (new or {}).get("uom", ""),
		"action": action,
		"eligible": action == "replace",
		"reason": reason,
		"qty_recalculated": False,
		"note": None,
	}


def _replace_change(old: dict, new: dict) -> dict:
	"""Keep the stored qty; when the unit changes, the old qty is meaningless, so take the recalculated one."""
	if not old.get("eligible"):
		return _change(old, new, "blocked", old.get("reason"))
	change = _change(old, new, "replace", None)
	if (old["uom"] or "") != (new.get("uom") or ""):
		change.update(
			new_qty=change["calculated_qty"],
			new_uom=change["calculated_uom"],
			qty_recalculated=True,
			note=_("qty recalculated (unit {0} → {1})").format(old["uom"], new.get("uom")),
		)
	return change


def _placeholder(selection_id: str) -> dict:
	return {"row_name": selection_id, "item_variant": "", "qty": 0, "uom": "", "attrs": {}}


def get_stale_rows(stale: list[dict], new_rows: list[dict]) -> list[dict]:
	"""Rows of the one item no longer in the Item BOM whose variants map onto ``new_rows``."""
	by_template = defaultdict(list)
	for row in stale:
		by_template[row["template"]].append(row)
	candidates = [rows for rows in by_template.values() if get_row_pairs(rows, new_rows)]
	return candidates[0] if len(candidates) == 1 else []


def _plan_template(template, selection_id, current, expected, stale) -> list[dict]:
	own = [row for row in current if row["template"] == template]
	new = {row["item_variant"]: row for row in expected if row["template"] == template}
	changes = [
		_change(row, new[row["item_variant"]], "unchanged", _("already matches recalculation"))
		for row in own
		if row["item_variant"] in new
	]
	old_rows = [row for row in own if row["item_variant"] not in new]
	new_rows = [row for variant, row in new.items() if variant not in {r["item_variant"] for r in own}]
	if not new_rows:
		reason = _("No recalculated Item BOM row was found.")
		return changes + [_change(row, None, "blocked", row.get("reason") or reason) for row in old_rows]
	old_rows = old_rows or get_stale_rows(stale, new_rows)
	pairs = get_row_pairs(old_rows, new_rows) if old_rows else {}
	if pairs is None:
		reason = _("Several rows could match; this change cannot be mapped row by row.")
		return changes + [_change(row, None, "blocked", reason) for row in old_rows]
	changes += [_replace_change(row, pairs[row["row_name"]]) for row in old_rows]
	paired = {row["item_variant"] for row in pairs.values()}
	missing = _("No existing Work Order row was found.")
	return changes + [
		_change(_placeholder(selection_id), row, "blocked", missing)
		for row in new_rows
		if row["item_variant"] not in paired
	]


def _block_shared_rows(changes: list[dict]) -> list[dict]:
	items_by_row = defaultdict(set)
	for change in changes:
		items_by_row[change["row_name"]].add(change["item"])
	reason = _("matches more than one selected Item BOM row; select one at a time")
	for change in changes:
		if change["action"] == "replace" and len(items_by_row[change["row_name"]]) > 1:
			change.update(action="blocked", eligible=False, reason=reason)
	return changes


def plan_item_changes(current: list[dict], expected: list[dict], selected: dict) -> list[dict]:
	"""Plan variant swaps for the selected Item BOM templates (``{template: selection_id}``)."""
	expected_templates = {row["template"] for row in expected}
	stale = [row for row in current if row["template"] not in expected_templates]
	changes = []
	for template in sorted(selected):
		for change in _plan_template(template, selected[template], current, expected, stale):
			changes.append({**change, "item": template, "selection_id": selected[template]})
	return _block_shared_rows(changes)


def get_item_bom_rows(doc) -> list:
	ipd = frappe.get_cached_doc("YRP Item Production Detail", doc.production_detail)
	processes = set(_processes(doc.process_name))
	return [row for row in ipd.get("item_bom") or [] if row.process_name in processes]


def get_current_accessory_rows(doc, ipd) -> list[dict]:
	cloth_templates = {row.cloth for row in ipd.get("cloth_detail") or [] if row.cloth}
	rows = []
	for row in doc.get("deliverables") or []:
		if not row.get("is_calculated") or not row.item_variant:
			continue
		if update_if_string_instance(row.get("set_combination")):
			continue
		template, attrs = get_variant_identity(row.item_variant)
		if template == doc.item or template in cloth_templates:
			continue
		eligible, reason = _row_eligibility(row)
		rows.append(
			{
				"row_name": row.name,
				"item_variant": row.item_variant,
				"template": template,
				"attrs": attrs,
				"qty": flt(row.qty),
				"uom": row.uom,
				"eligible": eligible,
				"reason": reason,
			}
		)
	return rows


def get_expected_accessory_rows(doc, ipd) -> list[dict]:
	if not any(
		row.item_variant and flt(row.quantity) > 0 for row in doc.get("work_order_calculated_items") or []
	):
		frappe.throw(_("Calculate Items on Work Order {0} before changing items.").format(doc.name))
	rows = []
	for row in _expected_accessories(doc, ipd, _processes(doc.process_name)):
		template, attrs = get_variant_identity(row["item_variant"])
		rows.append({**row, "template": template, "attrs": attrs})
	return rows


def get_change_item_preview(doc, selected) -> dict:
	bom_by_name = {row.name: row for row in get_item_bom_rows(doc)}
	selected_templates = {}
	for name in sorted(selected):
		if name in bom_by_name:
			selected_templates.setdefault(bom_by_name[name].item, name)
	skipped = [
		{"row_name": name, "reason": _("not an Item BOM row for this Work Order process")}
		for name in sorted(set(selected).difference(bom_by_name))
	]
	changes = []
	if selected_templates:
		ipd = frappe.get_cached_doc("YRP Item Production Detail", doc.production_detail)
		current = get_current_accessory_rows(doc, ipd)
		changes = plan_item_changes(current, get_expected_accessory_rows(doc, ipd), selected_templates)
	return {"supported": bool(bom_by_name), "changes": changes, "skipped": skipped}


def _get_change_item_work_order(work_order: str):
	doc = _open_submitted_work_order(work_order, "write")
	if doc.get("is_rework"):
		frappe.throw(_("Change Item is not available on a rework Work Order."))
	return doc


def _parse_selected(selected) -> list[str]:
	selected = frappe.parse_json(selected) if isinstance(selected, str) else selected
	return list(dict.fromkeys(selected or []))


def get_change_comment(change: dict) -> str:
	variants = (escape_html(change["old_variant"]), escape_html(change["new_variant"]))
	if change["qty_recalculated"]:
		return _("Change Item: {0} → {1} (qty recalculated: {2} {3} → {4} {5})").format(
			*variants, change["old_qty"], change["old_uom"], change["new_qty"], change["new_uom"]
		)
	return _("Change Item: {0} → {1} (quantity retained: {2})").format(*variants, change["old_qty"])


@frappe.whitelist()
def get_wo_bom_accessory_items(work_order: str) -> dict:
	doc = _get_change_item_work_order(work_order)
	rows = get_item_bom_rows(doc)
	if not rows:
		return {
			"supported": False,
			"message": _("This Work Order's process has no recalculable Item BOM rows."),
			"items": [],
		}
	items = [
		{
			"row_name": row.name,
			"branch": row.process_name,
			"item": row.item,
			"item_variant": row.item,
			"attributes": _("Attribute Mapping") if row.based_on_attribute_mapping else "",
			"qty": flt(row.qty_of_bom_item, 3),
			"uom": row.uom,
			"eligible": True,
			"reason": None,
		}
		for row in rows
	]
	return {"supported": True, "items": items}


@frappe.whitelist()
def get_wo_bom_accessory_change_preview(work_order: str, selected) -> dict:
	doc = _get_change_item_work_order(work_order)
	return get_change_item_preview(doc, _parse_selected(selected))


@frappe.whitelist(methods=["POST"])
def apply_bom_accessory_changes(work_order: str, selected) -> dict:
	frappe.db.get_value("YRP Work Order", work_order, "name", for_update=True)
	doc = _get_change_item_work_order(work_order)
	selected = _parse_selected(selected)
	preview = get_change_item_preview(doc, selected)
	applied, skipped = [], list(preview["skipped"])
	for change in preview["changes"]:
		if change["action"] == "unchanged":
			continue
		if change["action"] != "replace":
			skipped.append({key: change[key] for key in ("row_name", "old_variant", "reason")})
			continue
		values = {"item_variant": change["new_variant"]}
		if change["qty_recalculated"]:
			values.update(qty=change["new_qty"], pending_quantity=change["new_qty"], uom=change["new_uom"])
		frappe.db.set_value(DELIVERABLES_DOCTYPE, change["row_name"], values)
		applied.append(change)
	if applied:
		lines = [get_change_comment(change) for change in applied]
		doc.add_comment("Comment", "<br>".join(lines))
	return {"applied": applied, "skipped": skipped}
