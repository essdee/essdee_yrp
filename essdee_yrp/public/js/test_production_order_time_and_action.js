const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const scriptPath = path.join(__dirname, "production_order.js");

function buttonsFor(context) {
	const buttons = [];
	const sandbox = {
		__: (value) => value,
		frappe: { ui: { form: { on() {} } } },
	};
	vm.runInNewContext(fs.readFileSync(scriptPath, "utf8"), sandbox, { filename: scriptPath });
	const frm = { doc: { name: "PPO-1" }, add_custom_button(label, _action, group) { buttons.push(`${group}/${label}`); } };
	sandbox.add_time_and_action_buttons(frm, { copies: [], ...context });
	return buttons;
}

assert.deepEqual(buttonsFor({ can_create: true }), ["Time and Action/Create T&A"]);
assert.deepEqual(buttonsFor({ time_and_action: "TA-1", status: "In Progress", can_convert: true }), [
	"Time and Action/Update T&A",
	"Time and Action/Convert to Lot T&A",
]);
assert.deepEqual(buttonsFor({ time_and_action: "TA-1", status: "Frozen", can_convert: true }), ["Time and Action/Convert to Lot T&A"]);
assert.deepEqual(buttonsFor({ time_and_action: "TA-1", status: "Completed" }), []);
console.log("Production Order Time and Action button tests passed");
