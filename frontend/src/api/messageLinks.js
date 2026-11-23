import { plainTextFromHtml } from "../utils/documentValues.js"
import { hasWebDocumentPage, webDocumentPath } from "../router/webDocumentRoutes.js"

/** Document links seen in server messages, by their plain-text label; error text stays plain everywhere else. */
const linksByLabel = new Map()
const MAX_LINKS = 200
const DESK_ANCHOR = /<a\b[^>]*?\bhref="\/app\/([a-z0-9-]+)\/([^"/?#]+)"[^>]*>([\s\S]*?)<\/a>/gi
const PLAIN_DOCTYPE = /^[A-Za-z0-9][A-Za-z0-9 _-]*$/

const deskSlug = (doctype) => doctype.toLowerCase().replace(/[ _]+/g, "-")

/** Record Desk document anchors labelled "<doctype> <name>" (Frappe strips data attributes) so the label can be linked later. */
export function rememberMessageLinks(html) {
	for (const [, slug, encodedName, labelHtml] of String(html || "").matchAll(DESK_ANCHOR)) {
		const name = safeDecode(plainTextFromHtml(encodedName))
		const label = plainTextFromHtml(labelHtml)
		const doctype = label.endsWith(` ${name}`) ? label.slice(0, -name.length - 1) : ""
		if (!name || !PLAIN_DOCTYPE.test(doctype) || deskSlug(doctype) !== slug) continue
		linksByLabel.delete(label)
		linksByLabel.set(label, { doctype, name })
		if (linksByLabel.size > MAX_LINKS) linksByLabel.delete(linksByLabel.keys().next().value)
	}
}

function safeDecode(value) {
	try {
		return decodeURIComponent(value)
	} catch {
		return ""
	}
}

export function messageLinkHref(doctype, name) {
	if (hasWebDocumentPage(doctype)) return webDocumentPath(doctype, name)
	return `/app/${deskSlug(doctype)}/${encodeURIComponent(name)}`
}

/** Split message text into plain and linked segments for the labels a server message linked. */
export function messageSegments(text) {
	const message = String(text ?? "")
	const labels = [...linksByLabel.keys()].filter((label) => message.includes(label)).sort((a, b) => b.length - a.length)
	if (!labels.length) return message ? [{ text: message }] : []
	const pattern = new RegExp(`(${labels.map((label) => label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`)
	return message.split(pattern).filter(Boolean).map((part) => {
		const link = linksByLabel.get(part)
		return link ? { text: part, href: messageLinkHref(link.doctype, link.name) } : { text: part }
	})
}
