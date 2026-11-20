import { hasSystemManagerRole } from "../../components/navigation/sessionUser.js"
import { NO_PERMISSION_PATH } from "../../router/listPermission.js"

export const LAYOUT_BUILDER_PATH = "/layout-builder"

/** Guard result: only System Managers open the Layout Builder. */
export function getBuilderRedirect(boot = globalThis.window?.frappe?.boot) {
	return hasSystemManagerRole(boot) ? undefined : { path: NO_PERMISSION_PATH, query: { doctype: "Layout Builder" }, replace: true }
}
