import json
from pathlib import Path

import frappe
from frappe import _

WORKSPACE_EXPERIENCE = "workspace"
REGISTERED_EXPERIENCE = "Registered Experience"
CARD_IDS_PATH = Path(__file__).with_name("web_workspace_cards.json")
MAX_TITLE_LENGTH = 140
OVERRIDE_DOCTYPE = "SD YRP Workspace Override"


def get_card_ids():
	"""Card ids the /web catalogue (frontend departments/cardCatalogue.js) offers."""
	return frozenset(json.loads(CARD_IDS_PATH.read_text()))


def get_built_in_layouts():
	"""Every UI Layout not made in the Layout Builder."""
	return frappe.get_all(
		"YRP UI Layout",
		filters={"experience_key": ["!=", WORKSPACE_EXPERIENCE]},
		fields=["name", "render_mode", "experience_key", "config"],
		order_by="name asc",
	)


def get_reserved_layout_names():
	return {row.name for row in get_built_in_layouts()}


def get_built_in_department_layouts():
	"""Department layouts by name, with their default workspace keys."""
	return {
		row["name"]: {
			"name": row["name"],
			"experience_key": row["experience_key"],
			"workspaces": json.loads(row["config"])["experience_props"]["workspaces"],
		}
		for row in get_built_in_layouts()
		if row.render_mode == REGISTERED_EXPERIENCE
	}


def get_overrides():
	"""Saved department layout sections by layout name."""
	rows = frappe.get_all(OVERRIDE_DOCTYPE, fields=["layout", "sections"])
	return {row.layout: frappe.parse_json(row.sections) for row in rows}


def get_department_layouts():
	overrides = get_overrides()
	return [
		{**layout, "sections": overrides.get(name)}
		for name, layout in get_built_in_department_layouts().items()
	]


def get_department_workspaces():
	"""Overridden department layouts by department (experience) key, for /web boot."""
	built_ins = get_built_in_department_layouts()
	return {
		built_ins[name]["experience_key"]: {"layout": name, "sections": sections}
		for name, sections in get_overrides().items()
		if name in built_ins
	}


def get_layout_sections(config):
	props = json.loads(config or "{}").get("experience_props") or {}
	return (props.get(WORKSPACE_EXPERIENCE) or {}).get("sections", [])


def get_workspace_layouts():
	rows = frappe.get_all(
		"YRP UI Layout",
		filters={"experience_key": WORKSPACE_EXPERIENCE},
		fields=["name", "config", "disabled", "modified"],
		order_by="name asc",
	)
	return [
		{
			"name": row.name,
			"disabled": row.disabled,
			"modified": row.modified,
			"sections": get_layout_sections(row.config),
		}
		for row in rows
	]


@frappe.whitelist()
def get_builder_data():
	"""Existing builder layouts and the names they cannot take."""
	frappe.only_for("System Manager")
	return {
		"layouts": get_workspace_layouts(),
		"department_layouts": get_department_layouts(),
		"reserved_names": sorted(get_reserved_layout_names()),
	}


@frappe.whitelist(methods=["POST"])
def save_layout(title, sections, original_name=None):
	"""Create or update (and rename) a builder layout named `title`."""
	frappe.only_for("System Manager")
	title = validate_title(title, original_name)
	sections = validate_sections(frappe.parse_json(sections))
	config = json.dumps(
		{
			"schema_version": 1,
			"experience_props": {WORKSPACE_EXPERIENCE: {"title": title, "sections": sections}},
		},
		indent=1,
	)
	if original_name:
		get_workspace_layout(original_name)
		if original_name != title:
			frappe.rename_doc("YRP UI Layout", original_name, title)
		layout = frappe.get_doc("YRP UI Layout", title)
		layout.config = config
		layout.save()
	else:
		layout = frappe.get_doc(
			{
				"doctype": "YRP UI Layout",
				"layout_name": title,
				"render_mode": REGISTERED_EXPERIENCE,
				"experience_key": WORKSPACE_EXPERIENCE,
				"description": _("Built in the /web Layout Builder."),
				"config": config,
			}
		).insert()
	return {"name": layout.name}


@frappe.whitelist(methods=["POST"])
def delete_layout(name):
	frappe.only_for("System Manager")
	get_workspace_layout(name)
	frappe.delete_doc("YRP UI Layout", name)


@frappe.whitelist(methods=["POST"])
def save_department_override(layout, sections):
	"""Replace built-in department layout `layout`'s cards without touching the layout record."""
	frappe.only_for("System Manager")
	if layout not in get_built_in_department_layouts():
		frappe.throw(_("{0} is not a built-in department layout").format(frappe.bold(layout)))
	sections = json.dumps(validate_sections(frappe.parse_json(sections)))
	if frappe.db.exists(OVERRIDE_DOCTYPE, layout):
		override = frappe.get_doc(OVERRIDE_DOCTYPE, layout)
		override.sections = sections
		override.save()
	else:
		frappe.get_doc({"doctype": OVERRIDE_DOCTYPE, "layout": layout, "sections": sections}).insert()
	return {"name": layout}


@frappe.whitelist(methods=["POST"])
def reset_department_override(layout):
	"""Return built-in department layout `layout` to its default cards."""
	frappe.only_for("System Manager")
	if frappe.db.exists(OVERRIDE_DOCTYPE, layout):
		frappe.delete_doc(OVERRIDE_DOCTYPE, layout)


def get_workspace_layout(name):
	if frappe.db.get_value("YRP UI Layout", name, "experience_key") != WORKSPACE_EXPERIENCE:
		frappe.throw(_("{0} is not a Layout Builder layout").format(frappe.bold(name)))
	return name


def validate_title(title, original_name=None):
	title = (title or "").strip()
	if not title:
		frappe.throw(_("Layout title is required"))
	if len(title) > MAX_TITLE_LENGTH:
		frappe.throw(_("Layout title must be at most {0} characters").format(MAX_TITLE_LENGTH))
	if title in get_reserved_layout_names():
		frappe.throw(_("{0} is a built-in layout name. Choose another title.").format(frappe.bold(title)))
	if title != original_name and frappe.db.exists("YRP UI Layout", title):
		frappe.throw(
			_("A UI Layout named {0} already exists. Choose another title.").format(frappe.bold(title))
		)
	return title


def validate_sections(sections):
	if not isinstance(sections, list) or not sections:
		frappe.throw(_("Add at least one section"))
	card_ids = get_card_ids()
	placed = set()
	cleaned = []
	for section in sections:
		label = (section.get("label") or "").strip() if isinstance(section, dict) else ""
		cards = section.get("cards") if isinstance(section, dict) else None
		if not label:
			frappe.throw(_("Every section needs a name"))
		if not isinstance(cards, list) or not cards:
			frappe.throw(_("Section {0} has no cards").format(frappe.bold(label)))
		for card in cards:
			if card not in card_ids:
				frappe.throw(_("Unknown card {0}").format(frappe.bold(str(card))))
			if card in placed:
				frappe.throw(_("Card {0} is placed more than once").format(frappe.bold(card)))
			placed.add(card)
		cleaned.append({"label": label, "cards": cards})
	return cleaned
