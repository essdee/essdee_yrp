import { lockedDepartment } from "../../router/departmentLock.js"
import { canOpenList } from "../../router/listPermission.js"
import { getCatalogueCard } from "../cardCatalogue.js"
import { departments } from "../registry.js"
import { DEPARTMENT_CARD_SOURCES } from "../search/departmentCards.js"
import { getDepartmentWorkspace } from "./departmentWorkspaces.js"

/** Title and card-id sections for department `departmentKey`'s overridden landing, else the Layout Builder workspace in `lock`. */
export function getWorkspaceView(departmentKey, lock = lockedDepartment, boot = globalThis.window?.frappe?.boot) {
	const department = departments.find((item) => item.key === departmentKey)
	const override = department && getDepartmentWorkspace(department.key, boot)
	if (override) return { title: department.label, sections: override.sections }
	return { title: lock?.label || "Workspace", sections: lock?.sections || [] }
}

/** Launcher card for catalogue `entry`: its own label, keyed by catalogue id so same-named cards stay distinct. */
export const toLauncherCard = (entry) => ({ ...entry.card, key: entry.id })

/** Card keys each department's landing page would show the user, from the `get_department_capabilities` payload. */
async function getReadableCardKeys(departmentKeys, all) {
	const entries = await Promise.all(departmentKeys.map(async (key) => {
		const source = await DEPARTMENT_CARD_SOURCES[key](all)
		return [key, new Set(source.cards.map((card) => card.key))]
	}))
	return Object.fromEntries(entries)
}

/** Workspace lock `sections` (card ids) as launcher sections holding only the cards the owner department grants and whose list the user can read. */
export async function getReadableSections(sections, all = {}, boot = undefined) {
	const resolved = sections.map((section) => ({ label: section.label, cards: section.cards.map(getCatalogueCard).filter(Boolean) }))
	const departmentKeys = [...new Set(resolved.flatMap((section) => section.cards.map((entry) => entry.department.key)))]
	const readable = await getReadableCardKeys(departmentKeys, all)
	return resolved
		.map((section) => ({
			label: section.label,
			items: section.cards
				.filter((entry) => readable[entry.department.key].has(entry.card.key) && canOpenList(entry.card.to, boot))
				.map(toLauncherCard),
		}))
		.filter((section) => section.items.length)
}
