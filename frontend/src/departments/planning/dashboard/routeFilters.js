export const DASHBOARD_VIEW = "dashboard"
export const TRACKING_VIEW = "tracking"
export const PROCESS_STATUS_VIEW = "process-status"
const VIEWS = [DASHBOARD_VIEW, TRACKING_VIEW, PROCESS_STATUS_VIEW]

const list = (value) => [].concat(value ?? []).flatMap((item) => String(item).split(",")).map((item) => item.trim()).filter(Boolean)

const FILTER_KINDS = ["ppo", "lot", "process", "category"]

/** Tab, PPO Tracking filters, the Product Category of every tab and Show dispatched held in the route query. */
export function readTrackingQuery(query = {}) {
	return {
		view: VIEWS.includes(query.view) ? query.view : DASHBOARD_VIEW,
		filters: Object.fromEntries(FILTER_KINDS.map((kind) => [kind, list(query[kind])])),
		showDispatched: query.dispatched === "1",
	}
}

export function trackingQuery({ filters, showDispatched }) {
	const query = { view: TRACKING_VIEW }
	for (const kind of FILTER_KINDS) if (filters[kind]?.length) query[kind] = [...filters[kind]]
	if (showDispatched) query.dispatched = "1"
	return query
}

/** Query of a Dashboard drill-down: PPO Tracking with the PPOs or lots selected, keeping the Product Category. */
export function drillQuery(drill) {
	return trackingQuery({ filters: { ppo: drill.ppo, lot: drill.lot, process: [], category: drill.category || [] }, showDispatched: drill.dispatched })
}
