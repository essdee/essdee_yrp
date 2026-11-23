import { computed, ref, watch } from "vue"
import { getDocPermissions, getMeta } from "../api/frappe.js"
import { canRenameDocument } from "../utils/documentRename.js"
import { useDocumentPermissions } from "./useDocumentPermissions.js"

/** Menu-only "Rename" for DocumentActionStrip, shown only when Desk would offer it. */
export function useRenameAction(source, { fetchMeta = getMeta, fetchPermissions = getDocPermissions } = {}) {
	const visible = ref(false)
	const meta = ref(null)
	const permissions = useDocumentPermissions(() => [...source(), 0], () => Boolean(source()[0]), fetchPermissions)
	watch(() => source()[0], async (doctype, _old, onCleanup) => {
		let stale = false
		onCleanup(() => { stale = true })
		meta.value = null
		if (!doctype) return
		try {
			const docs = await fetchMeta(doctype)
			if (!stale) meta.value = docs.find((doc) => doc.name === doctype) || null
		} catch {
			// Rename stays hidden when the DocType cannot be read.
		}
	}, { immediate: true })
	watch(() => source().join("\n"), () => { visible.value = false })
	const action = computed(() => {
		const [, name] = source()
		if (!canRenameDocument({ meta: meta.value, permissions: permissions.value, name })) return null
		return { key: "rename", label: "Rename", icon: "pi pi-pencil", menuOnly: true, command: () => { visible.value = true } }
	})
	return { action, visible }
}
