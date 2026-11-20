import { departments, getWorkspacePaths } from "../departments/registry.js"
import { getDepartmentWorkspace } from "../departments/workspace/departmentWorkspaces.js"

export const LAYOUT_UNAVAILABLE_PATH = "/not-in-your-layout"
export const WORKSPACE_EXPERIENCE = "workspace"
export const WORKSPACE_HOME_PATH = "/workspace"

/** Pages card `<department>:<card key>` opens: the paths its department's workspace of that key owns. */
function getCardPaths(id) {
	const [departmentKey, cardKey] = String(id).split(":")
	const department = departments.find((item) => item.key === departmentKey)
	return (department && getWorkspacePaths(department)[cardKey]) || []
}

/** Lock for Layout Builder `sections` of card ids, homed at `home` ({ key, label, path }): the sections and the pages their cards own. */
function getWorkspaceLock(sections = [], home) {
	const known = sections.map((section) => ({
		label: section.label,
		cards: (section.cards || []).filter((id) => getCardPaths(id).length),
	}))
	const paths = known.flatMap((section) => section.cards.flatMap(getCardPaths))
	return { ...home, sections: known, paths: [...new Set(paths)] }
}

/** Department and workspace keys a user's registered YRP UI Layout narrows /web to, or null for the full permission-based view. */
export function getLockedDepartment(boot) {
	const uiConfig = boot?.ui_config
	const meta = uiConfig?.meta
	if (meta?.render_mode !== "Registered Experience") return null
	if (meta.experience_key === WORKSPACE_EXPERIENCE) {
		const layout = uiConfig.config?.experience_props?.workspace
		return getWorkspaceLock(layout?.sections, { key: WORKSPACE_EXPERIENCE, label: layout?.title || meta.department_layout, path: WORKSPACE_HOME_PATH })
	}
	const department = departments.find((item) => item.key === meta.experience_key)
	if (!department) {
		console.warn(`/web: no department for experience "${meta.experience_key}"; showing all workspaces`)
		return null
	}
	const override = getDepartmentWorkspace(department.key, boot)
	if (override && override.layout === meta.department_layout) return getWorkspaceLock(override.sections, { key: department.key, label: department.label, path: department.path })
	const workspaces = uiConfig.config?.experience_props?.workspaces
	return { ...department, workspaces: Array.isArray(workspaces) ? workspaces : Object.keys(getWorkspacePaths(department)) }
}

export const lockedDepartment = getLockedDepartment(globalThis.window?.frappe?.boot)

function getSegments(target) {
	return String((typeof target === "string" ? target : target?.path) || "").toLowerCase().split(/[?#]/)[0].split("/").filter(Boolean)
}

/** Whether a navigation page at `path` (string or route location) is hidden by the layout: another department, or a section no listed workspace owns. Document pages stay open so cross-department links work. */
export function isOutsideLayout(path, department = lockedDepartment, isDocument = false) {
	if (!department || isDocument) return false
	const [first, segment] = getSegments(path)
	if (!departments.some((item) => item.path === `/${first}`)) return false
	if (department.paths) return isOutsideWorkspace(getSegments(path), department.paths)
	if (!segment) return `/${first}` !== department.path
	const paths = getWorkspacePaths(department)
	return !department.workspaces.some((key) => paths[key]?.includes(`/${first}/${segment}`))
}

/** Whether a department page is outside the workspace `paths`: a landing needs one card under it, a section page must be a card page or below one. */
function isOutsideWorkspace(segments, paths) {
	const path = `/${segments.join("/")}`
	if (segments.length === 1) return !paths.some((cardPath) => cardPath.startsWith(`${path}/`))
	return !paths.some((cardPath) => path === cardPath || path.startsWith(`${cardPath}/`))
}

/** Whether `path` is a department landing the layout sends to its own home: one its department combines, or any landing for a workspace. */
function isHomeLanding(path, department) {
	if (department.paths) return departments.some((item) => item.path === path)
	return (department.combines || []).some((key) => departments.find((item) => item.key === key)?.path === path)
}

/** Whether a launcher card belongs to the user's layout. */
export function isWorkspaceInLayout(item, department = lockedDepartment) {
	return !isOutsideLayout(item.to, department)
}

/** Guard result: the workspaces page goes to the layout's department; navigation pages outside the layout show the layout notice. */
export function getLockedRedirect(to, department = lockedDepartment) {
	if (!department) return undefined
	const path = to.path.toLowerCase().replace(/\/+$/, "") || "/"
	if (path === department.path) return undefined
	if (path === "/" || isHomeLanding(path, department)) return { path: department.path, replace: true }
	const isDocument = Object.keys(to.params || {}).some((key) => key !== "pathMatch")
	if (!isOutsideLayout(path, department, isDocument)) return undefined
	return { path: LAYOUT_UNAVAILABLE_PATH, query: { from: to.fullPath || to.path }, replace: true }
}

/** Whether a back link would leave the layout. */
export function isLockedExit(path, department = lockedDepartment) {
	return Boolean(department) && (path === "/" || isOutsideLayout(path, department)) && !isHomeLanding(path, department)
}

export function getHomePath(department = lockedDepartment) {
	return department?.path || "/"
}

/** Guard result for the workspace home: only a workspace layout has one; everyone else goes to their own home. */
export function getWorkspaceHomeRedirect(department = lockedDepartment) {
	if (department?.key === WORKSPACE_EXPERIENCE) return undefined
	return { path: getHomePath(department), replace: true }
}
