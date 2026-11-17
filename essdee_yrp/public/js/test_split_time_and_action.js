const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const scriptPath = path.join(__dirname, "TimeAndAction", "time_and_action_dialogs.js");

function load() {
	const calls = { xcall: [], call: [], dialogs: [] };
	const frappe = {
		provide(name) {
			let target = sandbox;
			for (const part of name.split(".")) target = target[part] ||= {};
		},
		xcall: (method, args) => {
			calls.xcall.push([method, args]);
			return Promise.resolve([{ name: "LOT-2", item: "<b>TEE</b>", qty: 10 }]);
		},
		call: (options) => {
			calls.call.push(options);
			options.callback({ message: ["TA-2"] });
		},
		confirm: (_message, yes) => yes(),
		msgprint: (message) => calls.msgprint = message,
		utils: { escape_html: (value) => String(value).replace(/</g, "&lt;"), get_form_link: (_doctype, name) => `<a>${name}</a>` },
		ui: {
			Dialog: class {
				constructor(options) { this.options = options; calls.dialogs.push(this); }
				show() {}
				hide() { this.hidden = true; }
			},
		},
	};
	const sandbox = { __: (text, values = []) => text.replace(/\{(\d)\}/g, (_match, index) => values[index]), frappe };
	vm.runInNewContext(fs.readFileSync(scriptPath, "utf8"), sandbox, { filename: scriptPath });
	return { frappe, calls };
}

(async () => {
	const { frappe, calls } = load();
	let done = 0;
	frappe.production.time_and_action.open_split_dialog({ time_and_action: "TA-1", on_done: () => done++ });
	const dialog = calls.dialogs[0];
	const lots = dialog.options.fields.find((field) => field.fieldname === "lots");
	assert.equal(lots.fieldtype, "MultiSelectList");
	const options = await lots.get_data("tee");
	assert.deepEqual(JSON.parse(JSON.stringify(calls.xcall[0])), ["essdee_yrp.time_and_action.split.get_split_lots", { time_and_action: "TA-1", txt: "tee" }]);
	assert.deepEqual(JSON.parse(JSON.stringify(options)), [{ value: "LOT-2", label: "LOT-2", description: "&lt;b>TEE&lt;/b> · Qty 10" }]);
	dialog.options.primary_action({ lots: ["LOT-2"] });
	assert.equal(calls.call[0].method, "essdee_yrp.time_and_action.split.split_time_and_action");
	assert.deepEqual(JSON.parse(JSON.stringify(calls.call[0].args)), { time_and_action: "TA-1", lots: ["LOT-2"] });
	assert.equal(dialog.hidden, true);
	assert.equal(done, 1);
	assert.match(calls.msgprint.message, /TA-2.*LOT-2/);
})();
