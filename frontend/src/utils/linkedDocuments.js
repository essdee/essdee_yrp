import { documentLinkTarget } from "./linkTarget.js"

const DOCSTATUS_LABELS = { 0: "Draft", 1: "Submitted", 2: "Cancelled" }

/** Groups `frappe.desk.form.linked_with.get` output by doctype, skipping doctypes with nothing to show. */
export function linkedDocumentGroups(linked, currentPath = globalThis.location?.pathname) {
	return Object.entries(linked || {})
		.map(([doctype, entry]) => ({
			doctype,
			hiddenCount: Number(entry?.hidden_count || 0),
			rows: (entry?.docs || []).map((doc) => {
				const target = documentLinkTarget(doctype, doc.name, currentPath)
				const docstatus = Number(doc.docstatus || 0)
				return { name: doc.name, status: DOCSTATUS_LABELS[docstatus], docstatus, href: target.href, route: target.route }
			}),
		}))
		.filter((group) => group.rows.length || group.hiddenCount)
}
