/** Desk's `can_rename`: write permission on a saved document of a renamable, non-single DocType. */
export function canRenameDocument({ meta, permissions, name }) {
	return Boolean(name && permissions?.write && meta?.allow_rename && !meta?.issingle)
}

/** The current route with the param that held `oldName` pointing at `newName`; null when no param holds it. */
export function renamedLocation(route, oldName, newName) {
	const key = Object.keys(route?.params || {}).find((param) => route.params[param] === oldName)
	if (!key) return null
	return { name: route.name, params: { ...route.params, [key]: newName }, query: route.query, hash: route.hash }
}

export function documentRenamedToast(doctype, oldName, newName) {
	return { severity: "success", summary: `${doctype} ${oldName} renamed to ${newName}`, life: 3500 }
}

export const RENAME_POLL_MS = 1500
const wait = (ms) => new Promise((done) => setTimeout(done, ms))

/** Poll a queued rename (Desk's enqueue mode) until it lands; rejects with the background job's error. */
export async function waitForRename(doctype, oldName, newName, since, { fetchStatus, sleep = wait, interval = RENAME_POLL_MS } = {}) {
	for (;;) {
		const result = await fetchStatus(doctype, oldName, newName, since)
		if (result?.status === "done") return result.name || newName
		if (result?.status === "failed") throw new Error(result.error || "Unable to rename this document.")
		await sleep(interval)
	}
}
