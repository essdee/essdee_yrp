const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const scriptPath = path.join(__dirname, "TimeAndAction", "time_and_action_dialogs.js");
const read = (name) => fs.readFileSync(path.join(__dirname, "TimeAndAction", name), "utf8");

function load() {
	const calls = { call: [], dialogs: [] };
	const preview_rows = [{ action: "KNIT", work_station: null }, { action: "DYE", work_station: null }];
	const frappe = {
		provide(name) {
			let target = sandbox;
			for (const part of name.split(".")) target = target[part] ||= {};
		},
		call: (options) => {
			calls.call.push(options);
			if (options.method.endsWith("get_schedule_preview")) options.callback({ message: preview_rows });
		},
		utils: { escape_html: (value) => String(value) },
		ui: {
			Dialog: class {
				constructor(options) {
					this.options = options;
					this.fields_dict = { preview_html: { wrapper: {} } };
					calls.dialogs.push(this);
				}
				get_values() { return { master: "MASTER-1", start_date: "2026-11-02" }; }
				disable_primary_action() {}
				enable_primary_action() {}
				show() {}
			},
		},
		production: {
			ui: {
				TimeActionPreview: class {
					load_data(data) { calls.loaded = data; }
					get_work_stations() { return {}; }
					get_planned_suppliers() { return { KNIT: ["SUP-1", "SUP-2"] }; }
				},
			},
		},
	};
	const sandbox = { __: (text) => text, frappe };
	vm.runInNewContext(fs.readFileSync(scriptPath, "utf8"), sandbox, { filename: scriptPath });
	return { frappe, calls };
}

const { frappe, calls } = load();
const dialog = frappe.production.time_and_action.open_create_dialog({ against: "SD YRP Lot", against_id: "LOT-1", label: "Lot" });
dialog.options.secondary_action();
assert.deepEqual(JSON.parse(JSON.stringify(calls.loaded["MASTER-1"])).map((row) => row.planned_suppliers), [[], []]);
dialog.options.primary_action({ master: "MASTER-1", start_date: "2026-11-02" });
const create = calls.call.find((call) => call.method.endsWith("create_time_and_action"));
assert.deepEqual(JSON.parse(JSON.stringify(create.args.planned_suppliers)), { KNIT: ["SUP-1", "SUP-2"] });

const preview = read("TimeActionPreview.vue");
assert.match(preview, /<td class="sticky-col col4">Planned Suppliers<\/td>/);
assert.match(preview, /fieldtype: "MultiSelectList"/);

const update = read("TandAUpdate.vue");
assert.match(update, /essdee_yrp.time_and_action.suppliers.get_supplier_chips/);
assert.match(update, /suppliers: JSON.stringify\(values.suppliers \|\| \[\]\)/);
assert.match(update, /data.value.modified = r.message.modified/);
assert.match(update, /v-if="data.can_edit_suppliers"/);
assert.match(read("TimeActionReport.vue"), /:title="supplierChipTitle\(chip\)"/);
