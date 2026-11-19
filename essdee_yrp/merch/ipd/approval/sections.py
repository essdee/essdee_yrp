"""Approval review sections built from the IPD workspace values, each with its own warnings."""

from essdee_yrp.merch.ipd.approval.piece_weight import number


def warning(level, section, text):
	return {"level": level, "section": section, "text": text}


def cloth_by(values, attribute):
	found = {}
	for row in (values.get("cutting_cloths_json") or {}).get("items") or []:
		if row.get(attribute):
			found.setdefault(row[attribute], set()).add(row.get("Cloth"))
	return found


def get_panels(values, panel_attribute):
	panel_cloth = cloth_by(values, panel_attribute)
	panels = [
		{
			"panel": row["stiching_attribute_value"],
			"part": row.get("set_item_attribute_value") or "",
			"qty": row.get("quantity"),
			"category": row.get("category"),
			"cloth": sorted(cloth for cloth in panel_cloth.get(row["stiching_attribute_value"], []) if cloth),
		}
		for row in values.get("stiching_item_details") or []
	]
	bare = [panel["panel"] for panel in panels if not panel["cloth"]] if panel_cloth else []
	warnings = (
		[warning("danger", "panels", f"{panel_attribute}s with no cloth: {', '.join(bare)}.")] if bare else []
	)
	return panels, warnings


def contrast_panels(panel_colours, set_combos, panels, is_set):
	part_of = {panel["panel"]: panel["part"] for panel in panels}
	contrast = []
	for row in panel_colours:
		major = row["major"]
		part_colours = next((combo["parts"] for combo in set_combos if combo["major"] == major), {})
		differs = {
			panel: colour
			for panel, colour in row["panels"].items()
			if colour != (part_colours.get(part_of.get(panel)) if is_set else major)
		}
		if differs:
			contrast.append({"major": major, "panels": differs})
	return contrast


def colour_warnings(colours, panel_colours, colour_cloth):
	found = []
	blank = [row["major"] for row in panel_colours if any(not colour for colour in row["panels"].values())]
	if blank:
		found.append(warning("danger", "colours", f"Panel colour missing for: {', '.join(blank)}."))
	missing = [colour for colour in colours if colour not in colour_cloth] if colour_cloth else []
	if missing:
		found.append(warning("danger", "colours", f"Colours with no cloth mapping: {', '.join(missing)}."))
	return found


def cloth_warnings(values):
	found = []
	if not (values.get("cutting_cloths_json") or {}).get("items"):
		found.append(warning("danger", "colours", "No cloth mapping entered."))
	for cloth in values.get("cloth_detail") or []:
		if not cloth.get("required_gsm"):
			found.append(
				warning("warning", "colours", f"Cloth {cloth['name1'].strip()} has no required GSM.")
			)
	return found


def get_colours(values, panels, attributes):
	is_set = bool(values.get("is_set_item"))
	colours = [row["attribute_value"] for row in values.get("packing_attribute_details") or []]
	set_combos = [
		{"major": row["major_attribute"], "parts": row["val"]}
		for row in ((values.get("set_item_detail") or {}).get("values") or [] if is_set else [])
	]
	panel_colours = [
		{"major": row["major_attribute"], "panels": row["val"]}
		for row in (values.get("stiching_item_detail") or {}).get("values") or []
	]
	colour_cloth = cloth_by(values, attributes["packing"])
	section = {
		"packing": colours,
		"set_combos": set_combos,
		"contrast_panels": contrast_panels(panel_colours, set_combos, panels, is_set),
		"cloths": [
			{"name": cloth["name1"].strip(), "cloth": cloth["cloth"], "gsm": cloth.get("required_gsm")}
			for cloth in values.get("cloth_detail") or []
		],
		"colour_cloth": {
			colour: sorted(cloth.strip() for cloth in colour_cloth.get(colour, []) if cloth)
			for colour in colours
		}
		if colour_cloth
		else {},
	}
	return section, colour_warnings(colours, panel_colours, colour_cloth)


def accessories_by_process(values):
	found = {}
	for row in values.get("item_bom") or []:
		found.setdefault(row.get("process_name"), []).append(row["item"])
	return found


def embellishment_warnings(process, panels, stages, panel_names, panel_attribute):
	found = []
	if process not in stages:
		found.append(
			warning(
				"warning", "embellishment", f"{process} is set on panels but missing from the process list."
			)
		)
	unknown = [panel for panel in panels if panel not in panel_names]
	if unknown:
		found.append(
			warning(
				"danger",
				"embellishment",
				f"{process} uses unknown {panel_attribute.lower()}s: {', '.join(unknown)}.",
			)
		)
	return found


def core_processes(values):
	return [
		{"role": "Cutting", "process": values.get("cutting_process")},
		{
			"role": "Stitching",
			"process": values.get("stiching_process"),
			"in": values.get("stiching_in_stage"),
			"out": values.get("stiching_out_stage"),
		},
		{
			"role": "Packing",
			"process": values.get("packing_process"),
			"in": values.get("pack_in_stage"),
			"out": values.get("pack_out_stage"),
		},
	]


def get_embellishment(values, panel_names, panel_attribute):
	on_panels = values.get("emblishment_details_json") or {}
	processes = values.get("ipd_processes") or []
	stages = {row["process_name"]: row.get("in_stage") for row in processes}
	by_process = accessories_by_process(values)
	warnings = []
	embellishments = []
	for process, panels in on_panels.items():
		embellishments.append(
			{
				"process": process,
				"panels": panels,
				"stage": stages.get(process) or "",
				"accessories": by_process.get(process, []),
			}
		)
		warnings += embellishment_warnings(process, panels, stages, panel_names, panel_attribute)
	others = [
		{
			"process": row["process_name"],
			"stage": row.get("in_stage") or "",
			"accessories": by_process.get(row["process_name"], []),
		}
		for row in processes
		if row["process_name"] not in on_panels
	]
	cut_stage = values.get("stiching_in_stage") or "Cut"
	warnings += [
		warning(
			"warning",
			"embellishment",
			f"{row['process']} runs at {row['stage']} stage but is not mapped to any {panel_attribute.lower()}.",
		)
		for row in others
		if row["stage"] == cut_stage
	]
	if not processes:
		warnings.append(
			warning("info", "embellishment", "No processes beyond cutting, stitching and packing.")
		)
	section = {
		"embellishments": embellishments,
		"other_processes": others,
		"core_processes": core_processes(values),
	}
	return section, warnings


def mapping_summary(detail):
	"""BOM attribute mapping lines grouped by BOM value and quantity."""
	lines = {}
	for row in detail.get("rows") or []:
		line = lines.setdefault(row["index"], {"item": {}, "bom": {}, "qty": None})
		line[row["type"]][row["attribute"]] = row["attribute_value"]
		line["qty"] = row.get("quantity")
	grouped = {}
	for line in lines.values():
		key = (", ".join(str(value) for value in line["bom"].values()) or "as garment", line["qty"])
		grouped.setdefault(key, []).append(" ".join(line["item"].values()))
	return {
		"summary": [{"bom": bom, "qty": qty, "for": items} for (bom, qty), items in grouped.items()],
		"same": detail.get("same_attributes") or [],
	}


def accessory_row(row, bom_mappings):
	detail = bom_mappings.get(row.get("name")) if row.get("based_on_attribute_mapping") else None
	per_product = number(row.get("qty_of_product")) or 0
	per_bom = number(row.get("qty_of_bom_item")) or 0
	return {
		"item": row["item"],
		"process": row.get("process_name") or "",
		"stage": row.get("dependent_attribute_value") or "",
		"qty_of_product": per_product,
		"qty_of_bom_item": per_bom,
		"uom": row.get("uom") or "",
		"wastage_pct": number(row.get("wastage_pct")) or 0,
		"mapped": bool(row.get("based_on_attribute_mapping")),
		"mapping": mapping_summary(detail) if detail else None,
	}


def get_accessories(values, context):
	bom_mappings = context.get("bom_mappings") or {}
	accessories = [accessory_row(row, bom_mappings) for row in values.get("item_bom") or []]
	warnings = []
	for row in accessories:
		if not row["qty_of_bom_item"] or not row["qty_of_product"]:
			warnings.append(warning("danger", "accessories", f"{row['item']} has zero quantity."))
		if row["mapped"] and not (row["mapping"] or {}).get("summary"):
			warnings.append(
				warning(
					"warning",
					"accessories",
					f"{row['item']} is attribute-mapped but the mapping has no rows.",
				)
			)
	if not accessories:
		warnings.append(warning("danger", "accessories", "No accessories (Item BOM is empty)."))
	return accessories, warnings


def cloth_accessory_warnings(accessory, has_colour_rows, cloth_names):
	name = accessory["name"]
	weights, colours = accessory["weights"], accessory["colours"]
	found = []
	if not weights:
		found.append(("danger", f"{name} has no weight row."))
	elif any(not row["weight"] for row in weights):
		found.append(("danger", f"{name} has blank or zero weights."))
	if has_colour_rows and not colours:
		found.append(("warning", f"{name} has no colour / cloth mapping."))
	if any(not row["cloth"] or not row["colour"] for row in colours):
		found.append(("danger", f"{name} has colours without cloth or accessory colour."))
	unknown = sorted({row["cloth"] for row in colours if row["cloth"] and row["cloth"] not in cloth_names})
	if unknown:
		found.append(("danger", f"{name} uses cloth not in Cloth Detail: {', '.join(unknown)}."))
	return [warning(level, "cloth_accessories", text) for level, text in found]


def cloth_accessory(name, part, grid, colour_rows):
	keys = [key for key in grid.get("attributes") or [] if key not in ("Accessory", "Dia", "Weight")]
	return {
		"name": name.strip(),
		"part": part or "",
		"by": " / ".join(keys),
		"weights": [
			{
				"key": " / ".join(str(item.get(key)) for key in keys) or "All",
				"dia": item.get("Dia") or "",
				"weight": number(item.get("Weight")),
			}
			for item in grid.get("items") or []
			if item.get("Accessory") == name
		],
		"colours": [
			{
				"major": row.get("major_colour"),
				"colour": row.get("accessory_colour"),
				"cloth": (row.get("cloth_type") or "").strip(),
				"part": row.get("Part") or "",
			}
			for row in colour_rows
			if row.get("accessory") == name
		],
	}


def get_cloth_accessories(values):
	grid = values.get("cloth_accessory_json") or {}
	colour_rows = (values.get("stiching_accessory_json") or {}).get("items") or []
	cloth_names = {cloth["name1"].strip() for cloth in values.get("cloth_detail") or []}
	accessories, warnings = [], []
	for name, part in (values.get("accessory_clothtype_json") or {}).items():
		accessory = cloth_accessory(name, part, grid, colour_rows)
		accessories.append(accessory)
		warnings += cloth_accessory_warnings(accessory, bool(colour_rows), cloth_names)
	return accessories, warnings
