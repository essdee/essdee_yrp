"""Attribute mappings linked from an IPD are editable only while that IPD is editable."""

import frappe
from frappe import _

from essdee_yrp.merch.ipd.capabilities import is_approved
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


def get_lock(ipd, check_permission=True) -> tuple[str, type] | None:
	"""(message, exception) when the IPD's attribute mappings cannot change."""
	if is_approved(ipd):
		message = _("IPD {0} is approved. Revert the approval to change attribute mappings.")
		return message.format(ipd.name), frappe.ValidationError
	if check_permission and not frappe.has_permission(IPD, "write", doc=ipd):
		message = _("You need write permission on IPD {0} to change its attribute mappings.")
		return message.format(ipd.name), frappe.PermissionError
	return None


def get_mapping_lock(mapping, check_permission=True) -> tuple[str, type] | None:
	for name in get_linked_ipds(mapping):
		lock = get_lock(frappe.get_doc(IPD, name), check_permission)
		if lock:
			return lock
	return None


def is_internal_save(mapping) -> bool:
	flags = frappe.flags
	return bool(
		mapping.is_new()
		or flags.in_patch
		or flags.in_migrate
		or flags.in_install
		or mapping.flags.get("last_updated_by_sd_yrp_sync")
	)


def validate(mapping, method=None):
	"""Reject saving a mapping of an approved IPD, or of an IPD the user cannot write."""
	if is_internal_save(mapping):
		return
	generated = frappe.flags.get("generated_cloth_ipd_updates") or set()
	if generated and set(get_linked_ipds(mapping)) <= generated:
		return
	lock = get_mapping_lock(mapping, check_permission=not mapping.flags.ignore_permissions)
	if lock:
		frappe.throw(*lock)


def onload(mapping, method=None):
	if not mapping.is_new():
		lock = get_mapping_lock(mapping)
		mapping.set_onload("ipd_mapping_lock", lock[0] if lock else "")
