/** Injected by ModuleSidebar so a department's WorkspaceLauncher reports its permitted cards instead of rendering them. */
export const workspaceCardsSinkKey = Symbol("essdee-workspace-cards-sink")

/** Key of the card whose path is the longest prefix of `path`. */
export function getSelectedCardKey(cards, path) {
	let selected = { key: "", length: -1 }
	for (const card of cards) {
		const to = String(card.to || "").split(/[?#]/)[0]
		const matches = path === to || path.startsWith(`${to}/`)
		if (matches && to.length > selected.length) selected = { key: card.key, length: to.length }
	}
	return selected.key
}

/** Viewports where the module sidebar is an off-canvas drawer instead of a hover rail. */
export const DRAWER_MEDIA_QUERY = "(max-width: 900px), (hover: none)"

const PINNED_STORAGE_PREFIX = "essdee-module-sidebar-pinned:"

/** Whether `user` keeps the desktop module sidebar open; false when storage is unavailable. */
export function isSidebarPinned(user, storage = globalThis.localStorage) {
	try {
		return storage?.getItem(PINNED_STORAGE_PREFIX + user) === "1"
	} catch {
		return false
	}
}

export function saveSidebarPinned(user, pinned, storage = globalThis.localStorage) {
	try {
		storage?.setItem(PINNED_STORAGE_PREFIX + user, pinned ? "1" : "0")
	} catch {
		// Private mode or blocked storage: the choice lasts for this page only.
	}
}
