"""Planned suppliers per T&A action (information only) and live actual suppliers from Work Orders and Purchase Orders."""

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.time_and_action.create import LOT, TIME_AND_ACTION
from essdee_yrp.time_and_action.rules import LOCKED_STATUSES

WORK_ORDER = "YRP Work Order"
PURCHASE_ORDER = "Purchase Order"


def parse_planned_suppliers(value) -> dict[str, list[str]]:
	"""`{action: [supplier]}` from Desk/web JSON or a dict."""
	value = frappe.parse_json(value) if isinstance(value, str) else value
	return {action: list(suppliers or []) for action, suppliers in (value or {}).items()}


def append_planned_suppliers(doc, planned_suppliers) -> None:
	for action, suppliers in parse_planned_suppliers(planned_suppliers).items():
		for supplier in suppliers:
			doc.append("planned_suppliers", {"action": action, "supplier": supplier})


def validate_planned_suppliers(doc) -> None:
	"""Each (action, supplier) once, for a step of this T&A; unchanged once Frozen or Completed."""
	actions = {row.action for row in doc.details}
	seen = set()
	for row in doc.planned_suppliers:
		if row.action not in actions:
			frappe.throw(
				_("Planned Supplier row {0}: {1} is not an action of this T&A.").format(row.idx, row.action)
			)
		if (row.action, row.supplier) in seen:
			frappe.throw(
				_("Supplier {0} is planned twice for {1}.").format(row.supplier, frappe.bold(row.action))
			)
		seen.add((row.action, row.supplier))
	before = doc.get_doc_before_save()
	if before and before.status in LOCKED_STATUSES and get_planned_pairs(before) != get_planned_pairs(doc):
		frappe.throw(_("Time and Action {0} is {1} and cannot be changed.").format(doc.name, before.status))


def get_planned_pairs(doc) -> list[tuple]:
	return [(row.action, row.supplier) for row in doc.planned_suppliers]


@frappe.whitelist()
def set_planned_suppliers(time_and_action: str, action: str, suppliers: list | str) -> dict:
	"""Replace the planned suppliers of one action; returns the new `modified` and the T&A's chips."""
	doc = frappe.get_doc(TIME_AND_ACTION, time_and_action)
	doc.check_permission("write")
	suppliers = frappe.parse_json(suppliers) if isinstance(suppliers, str) else suppliers
	kept = [row for row in doc.planned_suppliers if row.action != action]
	doc.set("planned_suppliers", [row.as_dict(no_default_fields=True) for row in kept])
	append_planned_suppliers(doc, {action: suppliers})
	doc.save()
	return {"modified": str(doc.modified), "chips": get_supplier_chips(time_and_action)}


@frappe.whitelist()
def get_supplier_chips(time_and_action: str) -> dict[str, list[dict]]:
	"""Per action: planned suppliers first (in order), then suppliers with actual work that were not planned."""
	doc = frappe.get_doc(TIME_AND_ACTION, time_and_action)
	doc.check_permission("read")
	actuals = get_row_actuals(doc)
	chips = {}
	for row in doc.details:
		planned = [
			(item.supplier, item.supplier_name) for item in doc.planned_suppliers if item.action == row.action
		]
		chips[row.action] = build_chips(planned, actuals.get(row.action, []))
	return chips


def build_chips(planned: list[tuple], actuals: list[dict]) -> list[dict]:
	chips = {
		supplier: {"supplier": supplier, "supplier_name": name, "is_planned": 1, "actuals": []}
		for supplier, name in planned
	}
	for entry in actuals:
		chip = chips.setdefault(
			entry["supplier"],
			{
				"supplier": entry["supplier"],
				"supplier_name": entry["supplier_name"],
				"is_planned": 0,
				"actuals": [],
			},
		)
		chip["actuals"].append(entry)
	return list(chips.values())


def get_row_actuals(time_and_action) -> dict[str, list[dict]]:
	"""Per action, one entry per (document type, supplier) for the T&A's lots; read live, never stored."""
	doc = time_and_action
	if isinstance(doc, str):
		doc = frappe.get_doc(TIME_AND_ACTION, doc)
	lots = get_lots(doc)
	settings = get_action_settings([row.action for row in doc.details])
	if not lots:
		return {}
	actuals = {}
	for action, entry in get_work_order_actuals(lots, settings) + get_purchase_order_actuals(lots, settings):
		actuals.setdefault(action, []).append(entry)
	return actuals


def get_lots(doc) -> list[str]:
	"""Lot T&A: its lot; Production Order T&A: the lots linked to the order."""
	if doc.against == LOT:
		return [doc.against_id]
	return frappe.get_all(LOT, filters={"production_order": doc.against_id}, pluck="name")


def get_action_settings(actions: list[str]) -> dict[str, frappe._dict]:
	"""`{action: {process_name, item_groups}}` for the T&A's actions."""
	settings = {
		row.name: frappe._dict(process_name=row.process_name, item_groups=set())
		for row in frappe.get_all(
			"SD YRP Action", filters={"name": ["in", actions]}, fields=["name", "process_name"]
		)
	}
	groups = frappe.get_all(
		"SD YRP Action Item Group",
		filters={"parenttype": "SD YRP Action", "parent": ["in", actions]},
		fields=["parent", "item_group"],
	)
	for row in groups:
		settings[row.parent].item_groups.add(row.item_group)
	return settings


def get_work_order_actuals(lots: list[str], settings: dict) -> list[tuple[str, dict]]:
	"""Submitted Work Orders of the lots, matched to actions by Process; delivered/received pieces per supplier."""
	actions_by_process = {}
	for action, setting in settings.items():
		if setting.process_name:
			actions_by_process.setdefault(setting.process_name, []).append(action)
	if not actions_by_process:
		return []
	orders = frappe.get_list(
		WORK_ORDER,
		filters={"docstatus": 1, "lot": ["in", lots], "process_name": ["in", list(actions_by_process)]},
		fields=[
			"name",
			"process_name",
			"supplier",
			"supplier_name",
			"total_no_of_pieces_delivered",
			"total_no_of_pieces_received",
		],
		order_by="supplier, name",
	)
	totals = {}
	for order in orders:
		for action in actions_by_process[order.process_name]:
			entry = get_entry(totals, action, WORK_ORDER, order, ("delivered", "received"))
			entry["delivered"] += flt(order.total_no_of_pieces_delivered)
			entry["received"] += flt(order.total_no_of_pieces_received)
	return [(key[0], entry) for key, entry in totals.items()]


def get_purchase_order_actuals(lots: list[str], settings: dict) -> list[tuple[str, dict]]:
	"""Submitted Purchase Order lines of the lots, matched to actions by the line's Item Group."""
	actions_by_group = {}
	for action, setting in settings.items():
		for group in setting.item_groups:
			actions_by_group.setdefault(group, []).append(action)
	if not actions_by_group:
		return []
	lines = frappe.get_list(
		PURCHASE_ORDER,
		filters=[["docstatus", "=", 1], ["Purchase Order Item", "lot", "in", lots]],
		fields=[
			"name",
			"supplier",
			"supplier_name",
			"`tabPurchase Order Item`.item_code",
			"`tabPurchase Order Item`.item_group",
			"`tabPurchase Order Item`.qty",
			"`tabPurchase Order Item`.received_qty",
		],
		order_by="supplier, name",
	)
	item_groups = get_item_groups([line.item_code for line in lines if not line.item_group])
	totals = {}
	for line in lines:
		group = line.item_group or item_groups.get(line.item_code)
		for action in actions_by_group.get(group, []):
			entry = get_entry(totals, action, PURCHASE_ORDER, line, ("ordered", "received"))
			entry["ordered"] += flt(line.qty)
			entry["received"] += flt(line.received_qty)
	return [(key[0], entry) for key, entry in totals.items()]


def get_item_groups(item_codes: list[str]) -> dict[str, str]:
	if not item_codes:
		return {}
	rows = frappe.get_all(
		"Item", filters={"name": ["in", list(set(item_codes))]}, fields=["name", "item_group"]
	)
	return {row.name: row.item_group for row in rows}


def get_entry(totals: dict, action: str, doctype: str, source, quantity_fields: tuple) -> dict:
	"""The running total for (action, doctype, supplier), created on first use."""
	key = (action, doctype, source.supplier)
	if key not in totals:
		totals[key] = {
			"doctype": doctype,
			"supplier": source.supplier,
			"supplier_name": source.supplier_name or source.supplier,
			"documents": [],
			**dict.fromkeys(quantity_fields, 0.0),
		}
	entry = totals[key]
	if source.name not in entry["documents"]:
		entry["documents"].append(source.name)
	return entry
