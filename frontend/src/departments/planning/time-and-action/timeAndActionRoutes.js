/** Route name of a department's T&A "Update dates" page; the router adds one per Lot department. */
export function lotTimeAndActionUpdateRouteName(department) {
	return department === "planning" ? "planning-time-and-action-update" : `${department}-lot-time-and-action-update`
}
