/** Bulk Close/Reopen for YRP Purchase Orders; the server skips ineligible rows and gives a reason for each. */
export function openStatusBulkActions(setOpenStatus) {
	const action = (name, label, icon, done, close) => ({
		action: name,
		label,
		icon,
		severity: close ? "danger" : "primary",
		done,
		missed: "skipped",
		async run(rows) {
			const { done: names = [], skipped = [] } = await setOpenStatus(rows.map((row) => row.name), close)
			return { done: names, failed: skipped.map(({ name, reason }) => ({ name, error: reason })) }
		},
	})
	return [
		action("close", "Close", "pi pi-lock", "closed", true),
		action("reopen", "Reopen", "pi pi-lock-open", "reopened", false),
	]
}
