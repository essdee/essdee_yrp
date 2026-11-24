"""Recalculate Item BOM accessory deliverables on a submitted Work Order.

Delivered accessory rows are never touched; every other accessory row is
rebuilt from the same IPD calculation used by ``Calculate Items``.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cstr, escape_html, flt
from yrp.utils import update_if_string_instance

from essdee_yrp.garment_work_order import _validate_garment_work_order, get_deliverable_row_values
from essdee_yrp.work_order_actions import (
	_expected_accessories,
	_open_submitted_work_order,
	_processes,
)

DELIVERABLES_DOCTYPE = "YRP Work Order Deliverables"
PLAN_KEYS = ("added", "updated", "removed", "kept", "unchanged")


def can_recalculate_deliverables(doc, processes, ipd) -> bool:
	if doc.docstatus != 1 or doc.open_status != "Open" or doc.get("is_rework") or not ipd:
		return False
	if not doc.get("lot") or frappe.db.get_value("YRP Process", doc.process_name, "is_cloth_process"):
		return False
	return bool({row.process_name for row in ipd.get("item_bom") or []}.intersection(processes))


def plan_deliverable_recalculation(current, expected, locked, referenced=None) -> dict:
	"""Compare stored accessory rows with recalculated rows.

	``locked`` maps a delivered variant to its reason; ``referenced`` maps a row that a
	submitted GRN points to (so it must not be deleted) to its reason. Rows and expected
	rows may carry ``template``; an item whose variant changed while delivered is left alone.
	"""
	referenced = referenced or {}
	plan = {key: [] for key in PLAN_KEYS}
	expected_by_variant = {}
	for row in expected:
		target = expected_by_variant.setdefault(row["item_variant"], {**row, "qty": 0})
		target["qty"] = flt(target["qty"] + flt(row["qty"]), 3)
	current_by_variant = defaultdict(list)
	for row in current:
		current_by_variant[row["item_variant"]].append(row)
	frozen = _get_changed_delivered_templates(current, expected_by_variant, locked)

	for variant, rows in current_by_variant.items():
		new = expected_by_variant.get(variant)
		template = _template(rows[0])
		if template in frozen:
			plan["kept"].extend(_change(row, new, reason=frozen[template]) for row in rows)
		elif variant in locked:
			plan["kept"].extend(_change(row, new, reason=locked[variant]) for row in rows)
		elif any(row["name"] in referenced for row in rows) and _needs_new_row(rows, new):
			reason = next(referenced[row["name"]] for row in rows if row["name"] in referenced)
			plan["kept"].extend(_change(row, new, reason=reason) for row in rows)
		elif not new:
			plan["removed"].extend(_change(row, None) for row in rows)
		elif rows[0].get("uom") != new.get("uom"):
			plan["removed"].extend(_change(row, None) for row in rows)
			plan["added"].append(_change(None, new))
		else:
			first, extra = rows[0], rows[1:]
			old_qty = flt(sum(flt(row["qty"]) for row in rows), 3)
			bucket = "updated" if extra or flt(first["qty"], 3) != new["qty"] else "unchanged"
			plan[bucket].append({**_change(first, new), "old_qty": old_qty})
			plan["removed"].extend({**_change(row, None), "merged": True} for row in extra)

	for variant, new in expected_by_variant.items():
		if variant not in current_by_variant and _template(new) not in frozen:
			plan["added"].append(_change(None, new))
	return plan


def _template(row):
	return row.get("template") or row["item_variant"]


def _needs_new_row(rows, new) -> bool:
	"""True when the plan would delete a stored row: removed item, unit change, or merged duplicate."""
	return not new or rows[0].get("uom") != new.get("uom") or len(rows) > 1


def _get_changed_delivered_templates(current, expected_by_variant, locked) -> dict:
	"""Map each delivered item whose IPD variants changed to a 'use Change Item' reason."""
	current_variants = defaultdict(set)
	for row in current:
		current_variants[_template(row)].add(row["item_variant"])
	expected_variants = defaultdict(set)
	for row in expected_by_variant.values():
		expected_variants[_template(row)].add(row["item_variant"])
	frozen = {}
	for template, variants in current_variants.items():
		delivered = variants.intersection(locked)
		new_variants = expected_variants.get(template, set()) - variants
		if delivered and new_variants:
			frozen[template] = _("Kept (delivered) — use Change Item. IPD now uses {0}; {1} is {2}.").format(
				", ".join(sorted(new_variants)), sorted(delivered)[0], locked[sorted(delivered)[0]]
			)
	return frozen


def _change(old, new, reason=None) -> dict:
	source = old or new
	return {
		"row_name": old["name"] if old else None,
		"item_variant": source["item_variant"],
		"uom": (new or old).get("uom"),
		"old_qty": flt(old["qty"], 3) if old else None,
		"new_qty": flt(new["qty"], 3) if new else None,
		"reason": reason,
	}


def is_accessory_deliverable(row, excluded_templates) -> bool:
	if not row.get("is_calculated") or not row.item_variant:
		return False
	if update_if_string_instance(row.get("set_combination")):
		return False
	return _variant_template(row.item_variant) not in excluded_templates


def get_delivered_variants(work_order) -> dict:
	"""Map each item variant on a submitted Delivery Challan of this Work Order to that challan."""
	rows = frappe.db.sql(
		"""
		SELECT item.item_variant, MIN(dc.name) AS delivery_challan
		FROM `tabYRP Delivery Challan Item` item
		INNER JOIN `tabYRP Delivery Challan` dc ON dc.name = item.parent
		WHERE dc.work_order = %(work_order)s AND dc.docstatus = 1
		GROUP BY item.item_variant
		""",
		{"work_order": work_order},
		as_dict=True,
	)
	return {row.item_variant: row.delivery_challan for row in rows}


def get_grn_referenced_rows(row_names) -> dict:
	"""Map each deliverable row a submitted GRN item points to, to that GRN."""
	if not row_names:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT item.ref_docname, MIN(grn.name) AS goods_received_note
		FROM `tabYRP Goods Received Note Item` item
		INNER JOIN `tabYRP Goods Received Note` grn ON grn.name = item.parent
		WHERE item.ref_doctype = 'YRP Work Order Deliverables'
		  AND item.ref_docname IN %(row_names)s
		  AND grn.docstatus = 1
		GROUP BY item.ref_docname
		""",
		{"row_names": tuple(row_names)},
		as_dict=True,
	)
	return {
		row.ref_docname: _("referenced by Goods Received Note {0}, so it is kept").format(
			row.goods_received_note
		)
		for row in rows
	}


def _variant_template(item_variant) -> str:
	return frappe.get_cached_value("Item", item_variant, "variant_of") or item_variant


def get_recalculation_plan(doc) -> dict:
	_validate_garment_work_order(doc)
	processes = _processes(doc.process_name)
	ipd = frappe.get_cached_doc("YRP Item Production Detail", doc.production_detail)
	if not can_recalculate_deliverables(doc, processes, ipd):
		frappe.throw(_("Work Order {0} has no Item BOM accessories to recalculate.").format(doc.name))
	excluded_templates = {doc.item}
	if processes[:1] != [ipd.stiching_process]:
		# Outside Stitching, IPD cloth rows are process inputs, not cloth accessories.
		excluded_templates |= {row.cloth for row in ipd.get("cloth_detail") or [] if row.cloth}
	current = [row for row in doc.deliverables if is_accessory_deliverable(row, excluded_templates)]
	locked = {
		variant: _("delivered in Delivery Challan {0}").format(challan)
		for variant, challan in get_delivered_variants(doc.name).items()
	}
	for row in current:
		if round(flt(row.qty), 3) != round(flt(row.pending_quantity), 3):
			locked.setdefault(
				row.item_variant,
				_("already delivered (pending {0} of {1})").format(
					flt(row.pending_quantity, 3), flt(row.qty, 3)
				),
			)
	plan = plan_deliverable_recalculation(
		[
			{
				"name": row.name,
				"item_variant": row.item_variant,
				"template": _variant_template(row.item_variant),
				"qty": row.qty,
				"uom": row.uom,
			}
			for row in current
		],
		[
			{**row, "template": _variant_template(row["item_variant"])}
			for row in _expected_accessories(doc, ipd, processes)
		],
		locked,
		get_grn_referenced_rows([row.name for row in current]),
	)
	plan["has_changes"] = bool(plan["added"] or plan["updated"] or plan["removed"])
	return plan


def apply_recalculation_plan(doc, plan) -> None:
	"""Apply the plan through the update-after-submit save path."""
	removed = {row["row_name"] for row in plan["removed"]}
	updated = {row["row_name"]: row["new_qty"] for row in plan["updated"]}
	received_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
	if plan["added"] and not received_type:
		frappe.throw(_("Set Default Received Type in YRP Stock Settings first."))
	doc.set("deliverables", [row for row in doc.deliverables if row.name not in removed])
	for row in doc.deliverables:
		if row.name in updated:
			row.qty = updated[row.name]
			row.pending_quantity = updated[row.name]
	for change in plan["added"]:
		values = {
			"item_variant": change["item_variant"],
			"qty": change["new_qty"],
			"uom": change["uom"],
			"set_combination": "{}",
		}
		doc.append(
			"deliverables", get_deliverable_row_values(values, len(doc.deliverables), doc.lot, received_type)
		)
	for index, row in enumerate(doc.deliverables, start=1):
		row.idx = index
	doc.save()


def get_plan_summary_html(plan) -> str:
	labels = {"added": _("Added"), "updated": _("Updated"), "removed": _("Removed")}
	lines = [
		"{0}: {1} ({2} → {3} {4})".format(
			labels[key],
			escape_html(row["item_variant"]),
			"-" if row["old_qty"] is None else row["old_qty"],
			"-" if row["new_qty"] is None else row["new_qty"],
			escape_html(row["uom"] or ""),
		)
		for key in labels
		for row in plan[key]
	]
	return "<br>".join(lines)


@frappe.whitelist()
def get_recalculate_deliverables_preview(work_order: str) -> dict:
	doc = _open_submitted_work_order(work_order, "write")
	return get_recalculation_plan(doc)


@frappe.whitelist()
def apply_recalculate_deliverables(work_order: str, modified: str | None = None) -> dict:
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import _lock_work_order_deliverables

	_lock_work_order_deliverables(work_order)
	doc = _open_submitted_work_order(work_order, "write")
	if modified and cstr(doc.modified) != cstr(modified):
		frappe.throw(
			_("{0} was modified after you opened it. Please refresh and try again.").format(doc.name),
			frappe.TimestampMismatchError,
		)
	plan = get_recalculation_plan(doc)
	if plan["has_changes"]:
		apply_recalculation_plan(doc, plan)
		doc.add_comment(
			"Comment",
			_("Recalculated deliverables: {0} added, {1} updated, {2} removed.").format(
				len(plan["added"]), len(plan["updated"]), len(plan["removed"])
			)
			+ "<br>"
			+ get_plan_summary_html(plan),
		)
	return plan
