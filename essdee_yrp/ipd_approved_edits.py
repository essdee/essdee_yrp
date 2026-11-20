import frappe
from frappe.model import no_value_fields, table_fields
from frappe.utils import cint, cstr, flt

APPENDABLE_TABLE = "ipd_processes"
EMBELLISHMENT_FIELD = "emblishment_details_json"
# Packing setup, "based on other attribute" packing, and every combination grid
# (with the panel-wise matrices regenerated from them) stay editable once Approved.
COMBINATION_FIELDS = (
	"packing_combo",
	"packing_attribute_no",
	"auto_calculate",
	"packing_attribute_details",
	"based_on_other_attribute_mapping",
	"packing_mode",
	"packing_size_details",
	"packing_assortment_attributes",
	"packing_assortment_json",
	"set_item_combination_details",
	"is_same_packing_attribute",
	"stiching_item_combination_details",
	"cutting_attributes",
	"cutting_items_json",
	"cloth_attributes",
	"cutting_cloths_json",
	"panel_wise_consumption_matrix_json",
	"panel_wise_cloth_mapping_json",
	"accessory_attributes",
	"accessory_clothtype_json",
	"cloth_accessory_json",
	"stiching_accessory_json",
)
VIRTUAL_COMBINATION_FIELDS = ("set_item_detail", "stiching_item_detail")
APPROVED_EDIT_FIELDS = (
	APPENDABLE_TABLE,
	EMBELLISHMENT_FIELD,
	*COMBINATION_FIELDS,
	*VIRTUAL_COMBINATION_FIELDS,
)
NUMERIC_FIELDTYPES = ("Float", "Currency", "Percent")
INTEGER_FIELDTYPES = ("Int", "Check")


def get_approved_edit_changes(doc, before) -> tuple[list[str], bool]:
	"""Compare a save of an Approved IPD with its stored copy.

	Returns the labels of locked fields that changed, and whether an allowed edit
	(new IPD Processes rows, Embellishment panels, packing or combination changes) is present.
	"""
	locked = []
	allowed = False
	for df in doc.meta.fields:
		if df.fieldname == APPENDABLE_TABLE:
			appended, valid = get_appended_rows(doc, before)
			allowed = allowed or appended
			if not valid:
				locked.append(df.label)
		elif df.fieldname == EMBELLISHMENT_FIELD:
			panels_changed, valid = get_embellishment_change(doc, before)
			allowed = allowed or panels_changed
			if not valid:
				locked.append(df.label)
		elif df.fieldtype in no_value_fields and df.fieldtype not in table_fields:
			continue
		elif df.fieldname in COMBINATION_FIELDS:
			allowed = allowed or has_changed(doc, before, df)
		elif has_changed(doc, before, df):
			locked.append(df.label or df.fieldname)
	return locked, allowed


def has_changed(doc, before, df) -> bool:
	if df.fieldtype in table_fields:
		return get_rows(doc, df) != get_rows(before, df)
	return normalize(df, doc.get(df.fieldname)) != normalize(df, before.get(df.fieldname))


def get_appended_rows(doc, before) -> tuple[bool, bool]:
	"""Return (rows were appended, stored rows are untouched)."""
	df = doc.meta.get_field(APPENDABLE_TABLE)
	stored = get_rows(before, df)
	incoming = get_rows(doc, df)
	stored_names = {row.name for row in before.get(APPENDABLE_TABLE) or []}
	new_rows = (doc.get(APPENDABLE_TABLE) or [])[len(stored) :]
	untouched = incoming[: len(stored)] == stored and not any(row.name in stored_names for row in new_rows)
	return len(incoming) > len(stored), untouched


def get_embellishment_change(doc, before) -> tuple[bool, bool]:
	"""Return (panels changed, the embellishment processes are unchanged)."""
	incoming = frappe.parse_json(doc.get(EMBELLISHMENT_FIELD)) or {}
	stored = frappe.parse_json(before.get(EMBELLISHMENT_FIELD)) or {}
	if not isinstance(incoming, dict) or set(incoming) != set(stored):
		return False, False
	if not all(isinstance(panels, list) for panels in incoming.values()):
		return False, False
	return any(incoming[process] != stored[process] for process in stored), True


def get_rows(doc, df) -> list[tuple]:
	child_fields = [
		child for child in frappe.get_meta(df.options).fields if child.fieldtype not in no_value_fields
	]
	return [
		(row.name, *(normalize(child, row.get(child.fieldname)) for child in child_fields))
		for row in doc.get(df.fieldname) or []
	]


def normalize(df, value):
	if df.fieldtype in NUMERIC_FIELDTYPES:
		return flt(value)
	if df.fieldtype in INTEGER_FIELDTYPES:
		return cint(value)
	if value in (None, ""):
		return None
	if df.fieldtype == "JSON":
		return frappe.parse_json(value)
	return cstr(value)
