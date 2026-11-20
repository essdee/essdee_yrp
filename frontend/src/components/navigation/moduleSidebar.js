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
