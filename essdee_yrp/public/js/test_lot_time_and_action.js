const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const scriptPath = path.join(__dirname, "../../essdee_yrp/doctype/sd_yrp_lot/sd_yrp_lot.js");

function loadLotScript(adminRole, roles, status) {
	const settingReads = [];
	class Widget {
		load_data() {}
	}
	const context = {
		console,
		__: (value) => value,
		$: () => ({ empty() {} }),
		frappe: {
			ui: { form: { on() {} } },
			production: { ui: { TimeAction: Widget, TimeActionReport: Widget } },
			user: { has_role: (role) => roles.includes(role) },
			model: { can_write: () => true },
			db: {
				async get_value(doctype, name, fieldname) {
					assert.deepEqual([doctype, name, fieldname], ["SD YRP Time and Action", "TA-1", "status"]);
					return { message: { status } };
				},
				async get_single_value(doctype, fieldname) {
					settingReads.push([doctype, fieldname]);
					return adminRole;
				},
			},
		},
	};
	vm.runInNewContext(fs.readFileSync(scriptPath, "utf8"), context, { filename: scriptPath });
	return { context, settingReads };
}

async function revertButtons(adminRole, roles, status = "Completed") {
	const { context, settingReads } = loadLotScript(adminRole, roles, status);
	const buttons = [];
	const frm = {
		doc: { name: "LOT-1", __onload: { time_and_action: "TA-1" } },
		fields_dict: { time_and_action_html: { wrapper: null }, time_and_action_report_html: { wrapper: null } },
		add_custom_button(label) { buttons.push(label); },
	};
	await context.setup_time_and_action(frm);
	return { buttons, settingReads };
}

(async () => {
	{
		const { buttons, settingReads } = await revertButtons("Lot Planner", ["Lot Planner"]);
		assert.deepEqual(settingReads, [["SD YRP T and A Settings", "t_and_a_admin_role"]]);
		assert.deepEqual(buttons, ["Update T&A", "Revert T & A"]);
	}

	{
		const { buttons } = await revertButtons("Lot Planner", ["T & A Admin"]);
		assert.deepEqual(buttons, ["Update T&A"]);
	}

	{
		const { buttons } = await revertButtons("Lot Planner", ["Lot Planner"], "In Progress");
		assert.deepEqual(buttons, ["Update T&A", "Split T&A", "Revert T & A"]);
	}

	console.log("SD YRP Lot Time and Action role setting tests passed");
})().catch((error) => {
	console.error(error);
	process.exitCode = 1;
});
