import frappe
from frappe import _

from essdee_yrp.merch.ipd.fields import DOCTYPE as IPD

ITEM_MAPPING = "YRP Item Item Attribute Mapping"
DEPENDENT_MAPPING = "YRP Item Dependent Attribute Mapping"
BOM_MAPPING = "YRP Item BOM Attribute Mapping"


def get_linked_ipds(mapping) -> list[str]:
	"""Names of the IPDs that read this mapping."""
	if mapping.doctype == ITEM_MAPPING:
		names = frappe.get_all(
			"YRP IPD Item Attribute", filters={"parenttype": IPD, "mapping": mapping.name}, pluck="parent"
		)
	elif mapping.doctype == DEPENDENT_MAPPING:
		names = frappe.get_all(IPD, filters={"dependent_attribute_mapping": mapping.name}, pluck="name")
	else:
		names = frappe.get_all(
			"YRP Item BOM", filters={"parenttype": IPD, "attribute_mapping": mapping.name}, pluck="parent"
		)
		if mapping.get("item_production_detail"):
			names.append(mapping.item_production_detail)
	return sorted(set(names))


def get_mapping_lock(mapping) -> str:
	"""Why the user cannot change this mapping: they lack write on an IPD that reads it."""
	for name in get_linked_ipds(mapping):
		if not frappe.has_permission(IPD, "write", doc=name):
			return _("You need write permission on IPD {0} to change its attribute mappings.").format(name)
	return ""


def is_internal_save(mapping) -> bool:
	flags = frappe.flags
	return bool(
		mapping.is_new()
		or mapping.flags.ignore_permissions
		or flags.in_patch
		or flags.in_migrate
		or flags.in_install
		or mapping.flags.get("last_updated_by_sd_yrp_sync")
	)


def validate(mapping, method=None):
	"""Reject saving a mapping read by an IPD the user cannot write. Approval does not lock it."""
	if is_internal_save(mapping):
		return
	lock = get_mapping_lock(mapping)
	if lock:
		frappe.throw(lock, frappe.PermissionError)


def onload(mapping, method=None):
	if not mapping.is_new():
		mapping.set_onload("ipd_mapping_lock", get_mapping_lock(mapping))
