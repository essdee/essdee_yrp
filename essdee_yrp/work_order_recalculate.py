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
	_row_eligibility,
)

DELIVERABLES_DOCTYPE = "YRP Work Order Deliverables"
PLAN_KEYS = ("added", "updated", "removed", "kept", "unchanged")


def can_recalculate_deliverables(doc, processes, ipd) -> bool:
	if doc.docstatus != 1 or doc.open_status != "Open" or doc.get("is_rework") or not ipd:
		return False
	if not doc.get("lot") or frappe.db.get_value("YRP Process", doc.process_name, "is_cloth_process"):
		return False
	return bool({row.process_name for row in ipd.get("item_bom") or []}.intersection(processes))


def plan_deliverable_recalculation(current, expected, locked) -> dict:
	"""Compare stored accessory rows with recalculated rows; ``locked`` maps a delivered variant to its reason."""
	plan = {key: [] for key in PLAN_KEYS}
	expected_by_variant = {}
	for row in expected:
		target = expected_by_variant.setdefault(row["item_variant"], {**row, "qty": 0})
		target["qty"] = flt(target["qty"] + flt(row["qty"]), 3)
	current_by_variant = defaultdict(list)
	for row in current:
		current_by_variant[row["item_variant"]].append(row)

	for variant, rows in current_by_variant.items():
		new = expected_by_variant.get(variant)
		if variant in locked:
			plan["kept"].extend(_change(row, new, reason=locked[variant]) for row in rows)
			continue
		if not new:
			plan["removed"].extend(_change(row, None) for row in rows)
			continue
		first, extra = rows[0], rows[1:]
		if first.get("uom") != new.get("uom"):
			plan["removed"].extend(_change(row, None) for row in rows)
			plan["added"].append(_change(None, new))
			continue
		old_qty = flt(sum(flt(row["qty"]) for row in rows), 3)
		bucket = "updated" if extra or flt(first["qty"], 3) != new["qty"] else "unchanged"
		plan[bucket].append({**_change(first, new), "old_qty": old_qty})
		plan["removed"].extend({**_change(row, None), "merged": True} for row in extra)

	for variant, new in expected_by_variant.items():
		if variant not in current_by_variant:
			plan["added"].append(_change(None, new))
	return plan


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
	template = frappe.get_cached_value("Item", row.item_variant, "variant_of") or row.item_variant
	return template not in excluded_templates


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
		eligible, reason = _row_eligibility(row)
		if not eligible:
			locked.setdefault(row.item_variant, reason)
	plan = plan_deliverable_recalculation(
		[
			{"name": row.name, "item_variant": row.item_variant, "qty": row.qty, "uom": row.uom}
			for row in current
		],
		_expected_accessories(doc, ipd, processes),
		locked,
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
