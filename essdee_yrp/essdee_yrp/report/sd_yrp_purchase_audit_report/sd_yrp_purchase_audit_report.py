import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate

DIRECTIONS = ("inward", "outward")

TRANSFER_PURPOSES = "('Send to Warehouse', 'Receive at Warehouse')"
GRN = "sle.voucher_type = 'YRP Goods Received Note'"
WORK_ORDER_GRN = f"{GRN} AND grn.against = 'YRP Work Order'"
LOT_TRANSFER = "'SD YRP Lot Transfer'"
RECONCILIATION = "'YRP Stock Reconciliation'"
LEDGER_CONDITION = "sle.is_cancelled = 0 AND sle.docstatus < 2"

INWARD_COLUMNS = (
	(
		"po_grn",
		_("GRN Received (Purchase Order)"),
		f"{GRN} AND grn.against = 'Purchase Order' AND grn.is_return = 0",
	),
	("wo_grn", _("GRN Received (Work Order)"), f"{WORK_ORDER_GRN} AND grn.is_return = 0"),
	("wo_return_grn", _("WO Return GRN"), f"{WORK_ORDER_GRN} AND grn.is_return = 1"),
	("dc_received", _("Delivery Challan Received"), "sle.voucher_type = 'YRP Delivery Challan'"),
	("se_material_receipt", _("Stock Entry Material Receipt"), "se.purpose = 'Material Receipt'"),
	("received_warehouse", _("Stock Entry Warehouse Transfer In"), f"se.purpose IN {TRANSFER_PURPOSES}"),
	("added_stock", _("Stock Update Added"), "su.update_type = 'Add'"),
	("conversion_inward", _("Item Conversion In"), "sle.voucher_type = 'SD YRP Item Conversion'"),
	("reconciliation_in", _("Reconciliation In"), None),
	("lot_transfer_in", _("Lot Transfer In (Cross-Warehouse)"), None),
)
OUTWARD_COLUMNS = (
	("dc_qty", _("Delivery Challan Issued"), "sle.voucher_type = 'YRP Delivery Challan'"),
	("wo_grn_consumed", _("GRN Work Order Consumed"), f"{WORK_ORDER_GRN} AND grn.is_return = 0"),
	("wo_return_grn_out", _("WO Return GRN Out"), f"{WORK_ORDER_GRN} AND grn.is_return = 1"),
	("se_material_issue", _("Stock Entry Material Issue"), "se.purpose = 'Material Issue'"),
	("material_consumed", _("Material Consumed"), "se.purpose = 'Material Consumed'"),
	("stock_dispatch", _("Stock Entry Stock Dispatch"), "se.purpose = 'Stock Dispatch'"),
	("sent_warehouse", _("Stock Entry Warehouse Transfer Out"), f"se.purpose IN {TRANSFER_PURPOSES}"),
	("reduced_stock", _("Stock Update Reduced"), "su.update_type = 'Reduce'"),
	("conversion_outward", _("Item Conversion Out"), "sle.voucher_type = 'SD YRP Item Conversion'"),
	("reconciliation_out", _("Reconciliation Out"), None),
	("lot_transfer_out", _("Lot Transfer Out (Cross-Warehouse)"), None),
)
UNMAPPED_SOURCE = "CONCAT_WS(' ', sle.voucher_type, se.purpose, grn.against, su.update_type)"

INWARD_SUPPLIER = """CASE sle.voucher_type
	WHEN 'YRP Goods Received Note' THEN grn.supplier
	WHEN 'YRP Delivery Challan' THEN dc.supplier
	WHEN 'YRP Stock Entry' THEN se.transfer_supplier
	WHEN 'YRP Stock Update' THEN su.supplier
END"""

ITEM_EXPRESSION = "COALESCE(NULLIF(variant.variant_of, ''), variant.name)"

DIMENSIONS = (
	(ITEM_EXPRESSION, "item"),
	("sle.item", "item_variant"),
	("variant.item_group", "item_group"),
	("sle.warehouse", "warehouse"),
	("NULLIF(sle.received_type, '')", "received_type"),
)
DIMENSION_ALIASES = tuple(alias for _expression, alias in DIMENSIONS)
MONTH = "DATE_FORMAT({date}, '%%Y-%%m')"

FILTER_CONDITIONS = {
	"warehouse": "sle.warehouse = %(warehouse)s",
	"item": f"{ITEM_EXPRESSION} IN %(item)s",
	"item_variant": "sle.item = %(item_variant)s",
	"received_type": "sle.received_type = %(received_type)s",
	"item_group": """variant.item_group IN (
		SELECT child.name FROM `tabItem Group` child
		JOIN `tabItem Group` parent ON parent.name IN %(item_group)s
		WHERE child.lft >= parent.lft AND child.rgt <= parent.rgt)""",
}

MULTI_SELECT_FILTERS = ("item", "item_group")

BALANCE_KEY = "sle.item, sle.warehouse, IFNULL(sle.lot, ''), IFNULL(sle.received_type, '')"
BALANCE_LEDGER = f"""FROM `tabYRP Stock Ledger Entry` sle
	JOIN `tabItem` variant ON variant.name = sle.item
	WHERE {LEDGER_CONDITION} AND sle.posting_date <= %(balance_date)s"""
BALANCE_QUERY = f"""SELECT {BALANCE_KEY}, SUM(sle.qty) {BALANCE_LEDGER} {{conditions}}
	AND sle.voucher_type != {RECONCILIATION}
	GROUP BY {BALANCE_KEY}"""
RECONCILED_BALANCE_QUERY = f"""SELECT recon.item, recon.warehouse, recon.lot, recon.received_type,
	recon.qty_after_transaction + COALESCE(SUM(later.qty), 0)
	FROM (
		SELECT sle.item, sle.warehouse, IFNULL(sle.lot, '') AS lot, IFNULL(sle.received_type, '') AS received_type,
			sle.qty_after_transaction, sle.posting_datetime, sle.creation,
			ROW_NUMBER() OVER (PARTITION BY {BALANCE_KEY} ORDER BY sle.posting_datetime DESC, sle.creation DESC)
				AS position
		{BALANCE_LEDGER} {{conditions}} AND sle.voucher_type = {RECONCILIATION}
	) recon
	LEFT JOIN `tabYRP Stock Ledger Entry` later ON later.item = recon.item AND later.warehouse = recon.warehouse
		AND IFNULL(later.lot, '') = recon.lot AND IFNULL(later.received_type, '') = recon.received_type
		AND later.is_cancelled = 0 AND later.docstatus < 2 AND later.posting_date <= %(balance_date)s
		AND later.voucher_type != {RECONCILIATION}
		AND (later.posting_datetime, later.creation) > (recon.posting_datetime, recon.creation)
	WHERE recon.position = 1
	GROUP BY recon.item, recon.warehouse, recon.lot, recon.received_type, recon.qty_after_transaction"""
RECONCILIATION_DELTA_QUERY = f"""SELECT {", ".join(DIMENSION_ALIASES)}{{period}},
	IF(delta > 0, 'reconciliation_in', 'reconciliation_out') AS bucket, SUM(ABS(delta)) AS qty, NULL AS suppliers
	FROM (
		SELECT ledger.*,
			qty_after_transaction - COALESCE(LAG(qty_after_transaction) OVER key_order, 0)
				- running_qty + COALESCE(LAG(running_qty) OVER key_order, 0) AS delta
		FROM (
			SELECT {", ".join(f"{expression} AS {alias}" for expression, alias in DIMENSIONS)},
				IFNULL(sle.lot, '') AS lot, sle.voucher_type, sle.posting_date, sle.posting_datetime,
				sle.creation, sle.qty_after_transaction,
				SUM(IF(sle.voucher_type = {RECONCILIATION}, 0, sle.qty)) OVER (
					PARTITION BY {BALANCE_KEY} ORDER BY sle.posting_datetime, sle.creation ROWS UNBOUNDED PRECEDING
				) AS running_qty
			FROM `tabYRP Stock Ledger Entry` sle
			JOIN `tabItem` variant ON variant.name = sle.item
			WHERE {LEDGER_CONDITION} AND sle.posting_date <= %(to_date)s {{conditions}}
				AND (sle.item, sle.warehouse) IN (
					SELECT recon.item, recon.warehouse FROM `tabYRP Stock Ledger Entry` recon
					WHERE recon.voucher_type = {RECONCILIATION} AND recon.is_cancelled = 0
						AND recon.docstatus < 2 AND recon.posting_date BETWEEN %(from_date)s AND %(to_date)s)
		) ledger
		WHERE voucher_type = {RECONCILIATION}
		WINDOW key_order AS (PARTITION BY item_variant, warehouse, lot, received_type
			ORDER BY posting_datetime, creation)
	) reconciliation
	WHERE posting_date BETWEEN %(from_date)s AND %(to_date)s AND ROUND(delta, 9) != 0
	GROUP BY {", ".join(DIMENSION_ALIASES)}{{group_period}}, bucket"""


def execute(filters=None):
	filters = frappe._dict(filters or {})
	for field in MULTI_SELECT_FILTERS:
		filters[field] = get_filter_values(filters.get(field))
	validate_filters(filters)
	view = get_view(filters)
	months = get_months(filters) if view == "month_wise" else []
	data, unmapped = get_data(filters, view, months)
	return get_columns(view, months, unmapped, data), data


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def item_query(doctype, txt, searchfield, start, page_len, filters):
	"""Item (or variant, with filters.variant) options inside the selected Item Group trees, matching the report filters."""
	filters = frappe._dict(filters or {})
	item_group = get_filter_values(filters.item_group)
	variant_key = "variant.name" if filters.variant else ITEM_EXPRESSION
	conditions = [
		"item.disabled = 0",
		"item.has_variants = 0" if filters.variant else "IFNULL(item.variant_of, '') = ''",
		"(item.name LIKE %(txt)s OR item.item_name LIKE %(txt)s)",
	]
	if item_group:
		conditions.append(
			f"item.name IN (SELECT {variant_key} FROM `tabItem` variant WHERE {FILTER_CONDITIONS['item_group']})"
		)
	return frappe.db.sql(
		f"""SELECT item.name, item.item_name FROM `tabItem` item
		WHERE {" AND ".join(conditions)}
		ORDER BY item.name LIMIT %(start)s, %(page_len)s""",
		{"txt": f"%{txt}%", "item_group": item_group, "start": start, "page_len": page_len},
	)


def get_filter_values(value):
	"""MultiSelectList values as a tuple for SQL IN; a single name is accepted too."""
	if isinstance(value, str):
		value = frappe.parse_json(value) if value.startswith("[") else [value]
	return tuple(name for name in value or [] if name)


def validate_filters(filters):
	if not filters.get("from_date") or not filters.get("to_date") or not filters.get("warehouse"):
		frappe.throw(_("From Date, To Date and Warehouse are required."))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date."))


def get_view(filters):
	if not filters.get("summarized_view"):
		return "detailed"
	return "month_wise" if filters.get("month_wise_report") else "summarized"


def get_months(filters):
	"""Return YYYY-MM keys for every month touched by the date range."""
	month, last = getdate(filters.from_date).replace(day=1), getdate(filters.to_date)
	months = []
	while month <= last:
		months.append(month.strftime("%Y-%m"))
		month = add_months(month, 1)
	return months


def get_filter_sql(filters):
	return "".join(
		f" AND {condition}" for field, condition in FILTER_CONDITIONS.items() if filters.get(field)
	)


def get_bucket_expression():
	"""SQL CASE naming the report column each ledger row belongs to; unmapped sources are named after their voucher."""
	cases = [f"WHEN sle.voucher_type = {LOT_TRANSFER} THEN 'lot_transfer'"]
	for sign, columns in ((">", INWARD_COLUMNS), ("<", OUTWARD_COLUMNS)):
		cases += [
			f"WHEN sle.qty {sign} 0 AND {condition} THEN '{field}'"
			for field, _label, condition in columns
			if condition
		]
	unmapped = f"CONCAT(IF(sle.qty > 0, 'inward', 'outward'), ':', {UNMAPPED_SOURCE})"
	return f"CASE {' '.join(cases)} ELSE {unmapped} END"


def get_period(view, date):
	"""SELECT and GROUP BY fragments for the month column of the month-wise view."""
	if view != "month_wise":
		return "", ""
	return f", {MONTH.format(date=date)} AS month", ", month"


def get_ledger_rows(filters, view):
	"""Movement quantities per row and bucket; lot transfers keep their sign so they net out per row."""
	period, group_period = get_period(view, "sle.posting_date")
	selects = ", ".join(f"{expression} AS {alias}" for expression, alias in DIMENSIONS)
	return frappe.db.sql(
		f"""
		SELECT {selects}{period}, {get_bucket_expression()} AS bucket,
			SUM(IF(sle.voucher_type = {LOT_TRANSFER}, sle.qty, ABS(sle.qty))) AS qty,
			GROUP_CONCAT(DISTINCT IF(sle.qty > 0, {INWARD_SUPPLIER}, NULL)) AS suppliers
		FROM `tabYRP Stock Ledger Entry` sle
		JOIN `tabItem` variant ON variant.name = sle.item
		LEFT JOIN `tabYRP Goods Received Note` grn
			ON sle.voucher_type = 'YRP Goods Received Note' AND grn.name = sle.voucher_no
		LEFT JOIN `tabYRP Delivery Challan` dc ON sle.voucher_type = 'YRP Delivery Challan' AND dc.name = sle.voucher_no
		LEFT JOIN `tabYRP Stock Entry` se ON sle.voucher_type = 'YRP Stock Entry' AND se.name = sle.voucher_no
		LEFT JOIN `tabYRP Stock Update` su ON sle.voucher_type = 'YRP Stock Update' AND su.name = sle.voucher_no
		WHERE sle.qty != 0 AND {LEDGER_CONDITION} AND sle.voucher_type != {RECONCILIATION}
			AND sle.posting_date BETWEEN %(from_date)s AND %(to_date)s {get_filter_sql(filters)}
		GROUP BY {", ".join(DIMENSION_ALIASES)}{group_period}, bucket
		""",
		filters,
		as_dict=True,
	)


def get_reconciliation_rows(filters, view):
	"""In-range reconciliation changes per row, measured per lot against the balance just before each entry."""
	period, group_period = get_period(view, "posting_date")
	query = RECONCILIATION_DELTA_QUERY.format(
		conditions=get_filter_sql(filters), period=period, group_period=group_period
	)
	return frappe.db.sql(query, filters, as_dict=True)


def get_bucket_field(bucket, qty, unmapped):
	"""Report field and quantity for a ledger bucket; registers columns for unmapped voucher sources."""
	if bucket == "lot_transfer":
		return ("lot_transfer_in" if qty > 0 else "lot_transfer_out"), abs(qty)
	if ":" not in bucket:
		return bucket, qty
	direction, source = bucket.split(":", 1)
	label = f"{source} {_('In') if direction == 'inward' else _('Out')}"
	field = frappe.scrub(label)
	unmapped[field] = (label, direction)
	return field, qty


def get_bucket_rows(filters, view):
	"""Pivot ledger and reconciliation buckets into one row per dimension and period."""
	period = ("month",) if view == "month_wise" else ()
	rows, unmapped = {}, {}
	for ledger_row in get_ledger_rows(filters, view) + get_reconciliation_rows(filters, view):
		field, qty = get_bucket_field(ledger_row.bucket, flt(ledger_row.qty), unmapped)
		key = tuple(ledger_row[alias] for alias in DIMENSION_ALIASES + period)
		row = rows.setdefault(key, new_row(ledger_row, period))
		row[field] = row.get(field, 0.0) + qty
		row["suppliers"].update(ledger_row.suppliers.split(",") if ledger_row.suppliers else ())
	for row in rows.values():
		for field in unmapped:
			row.setdefault(field, 0.0)
		for direction in DIRECTIONS:
			row[f"total_{direction}"] = sum(row[field] for field in get_bucket_fields(direction, unmapped))
	return list(rows.values()), unmapped


def new_row(ledger_row, period=()):
	row = {alias: ledger_row[alias] for alias in DIMENSION_ALIASES + period}
	return {**row, "suppliers": set(), **dict.fromkeys(get_quantity_fields(), 0.0)}


def get_data(filters, view, months):
	rows, unmapped = get_bucket_rows(filters, view)
	if view == "month_wise":
		rows = get_month_rows(rows, months)
	openings = get_stock_balances(filters, add_days(filters.from_date, -1))
	balances = get_stock_balances(filters, filters.to_date)
	rows += get_static_rows(rows, openings, balances, months, unmapped)
	for row in rows:
		key = (row["item_variant"], row["warehouse"], row["received_type"] or "")
		row["suppliers"] = ", ".join(sorted(row["suppliers"]))
		row["opening_stock"] = openings.get(key, 0.0)
		row["stock_balance"] = balances.get(key, 0.0)
	return sorted(rows, key=lambda row: tuple(row[alias] or "" for alias in DIMENSION_ALIASES)), unmapped


def get_static_rows(rows, openings, balances, months, unmapped):
	"""Rows for stock that sat untouched through the range, so totals cover the whole location."""
	moved = {(row["item_variant"], row["warehouse"], row["received_type"] or "") for row in rows}
	keys = [key for key in set(openings) | set(balances) if key not in moved]
	if not keys:
		return []
	variants = list({key[0] for key in keys})
	fields = ["name", "variant_of", "item_group"]
	items = {
		item.name: item for item in frappe.get_all("Item", filters={"name": ["in", variants]}, fields=fields)
	}
	month_fields = [get_month_field(month, direction) for month in months for direction in DIRECTIONS]
	quantity_fields = (
		get_quantity_fields() + list(unmapped) + month_fields + ["total_inward", "total_outward"]
	)
	return [
		{
			"item": items[variant].variant_of or variant,
			"item_variant": variant,
			"item_group": items[variant].item_group,
			"warehouse": warehouse,
			"received_type": received_type or None,
			"suppliers": set(),
			**dict.fromkeys(quantity_fields, 0.0),
		}
		for variant, warehouse, received_type in keys
	]


def get_stock_balances(filters, balance_date):
	"""Closing qty at balance_date per variant, warehouse and received type, computed per lot like YRP Stock Balance.

	The latest Stock Reconciliation entry sets a lot's balance to its qty_after_transaction; later entries add qty.
	"""
	lot_balances = {}
	values = {**filters, "balance_date": balance_date}
	for query in (BALANCE_QUERY, RECONCILED_BALANCE_QUERY):
		rows = frappe.db.sql(query.format(conditions=get_filter_sql(filters)), values)
		lot_balances.update({tuple(row[:4]): flt(row[4]) for row in rows})
	balances = {}
	for (variant, warehouse, _lot, received_type), qty in lot_balances.items():
		key = (variant, warehouse, received_type)
		balances[key] = balances.get(key, 0.0) + qty
	return {key: qty for key, qty in balances.items() if round(qty, 9)}


def get_month_rows(rows, months):
	"""Fold per-month rows into one row per dimension with month inward/outward columns."""
	month_fields = [get_month_field(month, direction) for month in months for direction in DIRECTIONS]
	totals = ("total_inward", "total_outward")
	result = {}
	for row in rows:
		dimensions = {alias: row[alias] for alias in DIMENSION_ALIASES}
		target = result.setdefault(
			tuple(dimensions.values()),
			{**dimensions, "suppliers": set(), **dict.fromkeys(month_fields + list(totals), 0.0)},
		)
		target["suppliers"].update(row["suppliers"])
		for direction in DIRECTIONS:
			target[get_month_field(row["month"], direction)] += row[f"total_{direction}"]
		for field in totals:
			target[field] += row[field]
	return list(result.values())


def get_month_field(month, direction):
	return f"{month.replace('-', '_')}_{direction}"


def get_quantity_fields(direction=None):
	columns = {"inward": INWARD_COLUMNS, "outward": OUTWARD_COLUMNS}
	directions = (direction,) if direction else DIRECTIONS
	return [field for name in directions for field, _label, _condition in columns[name]]


def get_bucket_fields(direction, unmapped):
	return get_quantity_fields(direction) + [
		field for field, (_label, side) in unmapped.items() if side == direction
	]


def get_bucket_columns(direction, unmapped, data):
	"""Bucket columns of one direction that carry a quantity in at least one row."""
	columns = {"inward": INWARD_COLUMNS, "outward": OUTWARD_COLUMNS}[direction]
	labels = [(field, label) for field, label, _condition in columns]
	labels += sorted((field, label) for field, (label, side) in unmapped.items() if side == direction)
	return [qty_column(label, field) for field, label in labels if any(row.get(field) for row in data)]


def get_columns(view, months, unmapped, data):
	columns = [
		link_column(_("Item"), "item", "Item"),
		link_column(_("Item Variant"), "item_variant", "Item"),
		link_column(_("Item Group"), "item_group", "Item Group"),
		link_column(_("Warehouse"), "warehouse", "Warehouse"),
		link_column(_("Received Type"), "received_type", "YRP Received Type"),
		qty_column(_("Opening Stock"), "opening_stock"),
	]
	for month in months:
		label = getdate(f"{month}-01").strftime("%b %Y")
		columns.append(qty_column(f"{label} {_('Inward')}", get_month_field(month, "inward")))
		columns.append(qty_column(f"{label} {_('Outward')}", get_month_field(month, "outward")))
	detailed = view == "detailed"
	columns += get_bucket_columns("inward", unmapped, data) if detailed else []
	columns.append(qty_column(_("Total Inward"), "total_inward"))
	columns += get_bucket_columns("outward", unmapped, data) if detailed else []
	columns.append(qty_column(_("Total Outward"), "total_outward"))
	columns.append(qty_column(_("Stock Balance"), "stock_balance"))
	columns.append({"label": _("Suppliers"), "fieldname": "suppliers", "fieldtype": "Data", "width": 160})
	return columns


def link_column(label, fieldname, options):
	return {"label": label, "fieldname": fieldname, "fieldtype": "Link", "options": options, "width": 140}


def qty_column(label, fieldname):
	return {"label": label, "fieldname": fieldname, "fieldtype": "Float", "width": 110}
