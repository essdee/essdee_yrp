const STEPS = "essdee_yrp.time_and_action.steps";

/** Desk "Update Action" dialog: completed actions locked, undated ones removable, new ones added after the last completed action. */
export function open_update_actions(data, on_saved) {
    const state = { adds: [], removes: [], preview: null };
    const rows = () => state.preview?.rows || data.rows;
    const dialog = new frappe.ui.Dialog({
        title: __("Update Action · {0}", [data.name]),
        size: "large",
        fields: get_fields(rows, () => add_row()),
        primary_action_label: __("Confirm"),
        primary_action: () => confirm(),
    });

    function slot_index(after) {
        return after ? rows().findIndex((row) => row.action === after) + 1 : 0;
    }

    function slots() {
        const last_dated = rows().findLastIndex((row) => row.actual_date);
        const options = last_dated < 0 ? [{ label: __("At the top"), value: "" }] : [];
        rows().forEach((row, index) => {
            if (index >= last_dated) options.push({ label: __("After {0}", [row.action]), value: row.action });
        });
        return options;
    }

    function render() {
        dialog.fields_dict.rows_html.$wrapper.html(rows_table(rows(), state.adds, state.removes));
        dialog.fields_dict.rows_html.$wrapper.find("[data-action]").on("click", (event) => toggle_row(event.currentTarget.dataset.action));
        dialog.fields_dict.impact_html.$wrapper.html(impact_html(state));
        const options = slots();
        dialog.set_df_property("after_action", "options", options);
        dialog.set_value("after_action", options[0]?.value || "");
    }

    function refresh(adds, removes) {
        if (!adds.length && !removes.length) {
            Object.assign(state, { adds, removes, preview: null });
            return render();
        }
        frappe.call({
            method: `${STEPS}.preview_update_actions`,
            args: { time_and_action: data.name, add: adds, remove: removes },
            callback: (r) => {
                Object.assign(state, { adds, removes, preview: r.message });
                render();
            },
        });
    }

    function toggle_row(action) {
        if (state.adds.some((item) => item.action === action)) {
            return refresh(state.adds.filter((item) => item.action !== action), state.removes);
        }
        const removes = state.removes.includes(action) ? state.removes.filter((name) => name !== action) : [...state.removes, action];
        refresh(state.adds, removes);
    }

    function add_row() {
        const values = dialog.get_values(true);
        if (!values.action) return frappe.msgprint(__("Select an Action."));
        const item = {
            action: values.action,
            lead_time: cint(values.lead_time),
            after_action: values.after_action || null,
            depends_on: values.depends_on || [],
            required_by: values.required_by || [],
            work_station: values.work_station || null,
        };
        refresh([...state.adds, item], state.removes);
        for (const field of ["action", "work_station", "depends_on", "required_by"]) dialog.set_value(field, field.endsWith("_on") || field.endsWith("_by") ? [] : "");
    }

    function confirm() {
        if (!state.adds.length && !state.removes.length) return frappe.msgprint(__("Add or remove at least one action."));
        frappe.call({
            method: `${STEPS}.update_actions`,
            args: { time_and_action: data.name, add: state.adds, remove: state.removes },
            freeze: true,
            callback: () => {
                dialog.hide();
                frappe.show_alert({ message: __("Actions updated"), indicator: "green" });
                on_saved();
            },
        });
    }

    dialog.fields_dict.depends_on.df.get_data = () => rows().slice(0, slot_index(dialog.get_value("after_action"))).map((row) => ({ value: row.action, description: "" }));
    dialog.fields_dict.required_by.df.get_data = () => rows().slice(slot_index(dialog.get_value("after_action"))).filter((row) => !row.actual_date).map((row) => ({ value: row.action, description: "" }));
    dialog.fields_dict.work_station.get_query = () => ({ filters: { action: dialog.get_value("action") || "" } });
    dialog.fields_dict.action.df.onchange = () => {
        const action = dialog.get_value("action");
        if (action) frappe.db.get_value("SD YRP Action", action, "lead_time").then((r) => dialog.set_value("lead_time", r.message?.lead_time || 1));
    };
    dialog.fields_dict.after_action.df.onchange = () => {
        const after = dialog.get_value("after_action");
        dialog.set_value("depends_on", after ? [after] : []);
        dialog.set_value("required_by", []);
    };
    render();
    dialog.show();
}

function get_fields(rows, add_row) {
    return [
        { fieldtype: "HTML", fieldname: "rows_html" },
        { fieldtype: "Section Break", label: __("Add an action") },
        { fieldtype: "Link", fieldname: "action", label: __("Action"), options: "SD YRP Action" },
        { fieldtype: "Int", fieldname: "lead_time", label: __("Lead Time (days)"), default: 1 },
        { fieldtype: "Select", fieldname: "after_action", label: __("Position"), options: [] },
        { fieldtype: "Column Break" },
        { fieldtype: "MultiSelectList", fieldname: "depends_on", label: __("Depends On"), get_data: () => [] },
        { fieldtype: "MultiSelectList", fieldname: "required_by", label: __("Must finish before"), get_data: () => [] },
        { fieldtype: "Link", fieldname: "work_station", label: __("Work Station"), options: "YRP Work Station" },
        { fieldtype: "Section Break" },
        { fieldtype: "Button", fieldname: "add_button", label: __("Add to list"), click: add_row },
        { fieldtype: "HTML", fieldname: "impact_html" },
    ];
}

function rows_table(rows, adds, removes) {
    const body = rows.map((row, index) => {
        const is_new = adds.some((item) => item.action === row.action);
        const date = row.actual_date ? __("Done {0}", [format_date(row.actual_date)]) : format_date(row.rescheduled_date);
        const control = row.actual_date
            ? `<span class="text-muted">${__("Locked")}</span>`
            : `<a data-action="${frappe.utils.escape_html(row.action)}" class="${is_new ? "text-muted" : "text-danger"}">${is_new ? __("Undo add") : __("Remove")}</a>`;
        const style = row.actual_date ? "background:#e8f5e9" : is_new ? "background:#fff8e1" : "";
        const tag = is_new ? ` <span class="indicator-pill orange no-indicator-dot">${__("New")}</span>` : "";
        return `<tr style="${style}"><td>${index + 1}</td><td><b>${frappe.utils.escape_html(row.action)}</b>${tag}</td><td>${row.lead_time}</td><td>${date}</td><td class="text-right">${control}</td></tr>`;
    });
    for (const action of removes) {
        const name = frappe.utils.escape_html(action);
        body.push(`<tr class="text-muted"><td></td><td><s>${name}</s></td><td></td><td>${__("Removing")}</td><td class="text-right"><a data-action="${name}">${__("Undo remove")}</a></td></tr>`);
    }
    const help = __("Completed actions are locked. Remove actions that are not dated yet, or add new ones after the last completed action.");
    return `<p class="text-muted">${help}</p><div style="max-height:300px;overflow:auto"><table class="table table-bordered table-sm"><thead><tr><th>#</th><th>${__("Action")}</th><th>${__("Lead Time")}</th><th>${__("Rescheduled Date")}</th><th></th></tr></thead><tbody>${body.join("")}</tbody></table></div>`;
}

function impact_html(state) {
    const lines = [
        ...state.removes.map((action) => __("Remove {0}", [action])),
        ...state.adds.map((item) => __("Add {0} ({1} days)", [item.action, item.lead_time])),
    ];
    if (!lines.length) return `<p class="text-muted">${__("Add or remove actions to see the effect on delivery.")}</p>`;
    const days = state.preview?.delivery_days_moved || 0;
    const moves = __("Expected delivery {0} → {1}", [format_date(state.preview?.delivery_date_before), format_date(state.preview?.delivery_date_after)]);
    const count = days ? `${days > 0 ? "+" : "-"}${Math.abs(days)} ${Math.abs(days) === 1 ? __("working day") : __("working days")}` : __("no change");
    const tone = days > 0 ? "alert-danger" : "alert-success";
    return `<ul>${lines.map((line) => `<li>${frappe.utils.escape_html(line)}</li>`).join("")}</ul><div class="alert ${tone}"><b>${moves}, ${count}</b></div>`;
}

function format_date(value) {
    return value ? String(value).slice(0, 10).split("-").reverse().join("-") : "";
}
