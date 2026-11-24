const ITEM_QUERY =
	"essdee_yrp.essdee_yrp.report.sd_yrp_purchase_audit_report.sd_yrp_purchase_audit_report.item_query";

const STOCK_LEDGER = "SD YRP Stock Ledger";

const get_item_filters = () => ({
	item_group: frappe.query_report.get_filter_value("item_group") || [],
});

frappe.query_reports["SD YRP Purchase Audit Report"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
			on_change: async (report) => {
				const supplier = report.get_filter_value("supplier");
				const warehouses = supplier
					? await frappe.db.get_list("Warehouse", {
							filters: { supplier, disabled: 0 },
							fields: ["name", "eyp_display_name"],
							limit: 2,
						})
					: [];
				const only = warehouses.length === 1 ? warehouses[0] : null;
				const warehouse = only?.name || "";
				// Warehouse shows its title in links; an empty title would blank the input.
				if (only) frappe.utils.add_link_title("Warehouse", only.name, only.eyp_display_name || only.name);
				if (report.get_filter_value("warehouse") !== warehouse) {
					report.set_filter_value("warehouse", warehouse);
				} else {
					report.refresh();
				}
			},
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => {
				const supplier = frappe.query_report.get_filter_value("supplier");
				return { filters: supplier ? { supplier, disabled: 0 } : { disabled: 0 } };
			},
		},
		{
			fieldname: "item",
			label: __("Item"),
			fieldtype: "MultiSelectList",
			options: "Item",
			get_data: (txt) =>
				frappe.xcall("frappe.desk.search.search_link", {
					doctype: "Item",
					txt,
					query: ITEM_QUERY,
					filters: get_item_filters(),
				}),
		},
		{
			fieldname: "item_variant",
			label: __("Item Variant"),
			fieldtype: "Link",
			options: "Item",
			get_query: () => ({ query: ITEM_QUERY, filters: { ...get_item_filters(), variant: 1 } }),
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "MultiSelectList",
			options: "Item Group",
			get_data: (txt) => frappe.db.get_link_options("Item Group", txt),
			on_change: (report) => {
				if (report.get_filter_value("item")?.length || report.get_filter_value("item_variant")) {
					report.set_filter_value({ item: [], item_variant: "" });
				} else {
					report.refresh();
				}
			},
		},
		{
			fieldname: "received_type",
			label: __("Received Type"),
			fieldtype: "Link",
			options: "YRP Received Type",
		},
		{
			fieldname: "summarized_view",
			label: __("Summarized View"),
			fieldtype: "Check",
			on_change: (report) => {
				const is_summarized = report.get_filter_value("summarized_view");
				if (!is_summarized && report.get_filter_value("month_wise_report")) {
					report.set_filter_value("month_wise_report", 0);
				} else {
					report.refresh();
				}
			},
		},
		{
			fieldname: "month_wise_report",
			label: __("Month-wise Report"),
			fieldtype: "Check",
			depends_on: "eval:doc.summarized_view",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname !== "item_variant" || !data?.item_variant) {
			return value;
		}
		const params = new URLSearchParams({
			from_date: frappe.query_report.get_filter_value("from_date"),
			to_date: frappe.query_report.get_filter_value("to_date"),
			warehouse: data.warehouse,
			item: data.item_variant,
		});
		if (data.received_type) {
			params.set("received_type", data.received_type);
		}
		const url = `/app/query-report/${encodeURIComponent(STOCK_LEDGER)}?${params}`;
		return `${value} <a href="${url}" target="_blank" title="${__("Open Stock Ledger")}">${__("Ledger")}</a>`;
	},
};
