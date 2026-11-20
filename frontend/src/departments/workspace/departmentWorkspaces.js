/** Saved Layout Builder sections replacing department `key`'s built-in layout (`{ layout, sections }`), or null. */
export function getDepartmentWorkspace(key, boot = globalThis.window?.frappe?.boot) {
	return boot?.ui_config?.department_workspaces?.[key] || null
}
