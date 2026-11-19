const LOT_TAB_PREFIX = "lot:"

/** Tab key for a linked Lot, kept apart from the fixed PPO tab keys. */
export function lotTabKey(lot) {
	return `${LOT_TAB_PREFIX}${lot}`
}

export function lotFromTabKey(key) {
	return String(key || "").startsWith(LOT_TAB_PREFIX) ? String(key).slice(LOT_TAB_PREFIX.length) : ""
}

/** Message for a Lot tab whose workspace could not load; permission errors name the Lot. */
export function lotTabErrorMessage(reason, lot) {
	if (reason?.exc_type === "PermissionError" || Number(reason?.status) === 403)
		return `You do not have permission to view Lot ${lot}.`
	if (reason?.exc_type === "DoesNotExistError" || Number(reason?.status) === 404)
		return `Lot ${lot} no longer exists.`
	return reason?.message || `Unable to load Lot ${lot}.`
}
