/** Desk's submit/cancel sounds for /web document lifecycle calls. */

// Whitelisted methods whose whole job is to submit or cancel a document.
const METHOD_SOUNDS = new Map([
	["submit_document", "submit"],
	["cancel_document", "cancel"],
	["submit_erp_invoice", "submit"],
	["submit_lot_transfer", "submit"],
	["submit_bulk_lot_transfer", "submit"],
	["submit_delivery_challan", "submit"],
	["cancel_vendor_bill", "cancel"],
	["cancel_laysheet", "cancel"],
])

// `action` / `command` values of the change_*_status and execute_*_command endpoints.
const COMMAND_SOUNDS = new Map([
	["submit", "submit"],
	["cancel", "cancel"],
	["cancel_linked_document", "cancel"],
])

const players = new Map()

/** Sound name ("submit" / "cancel") for a successful whitelisted call, else "". */
export function getDocumentSound(method, args = {}) {
	const command = COMMAND_SOUNDS.get(args?.command) || COMMAND_SOUNDS.get(args?.action)
	if (command) return command
	if ([true, 1, "1"].includes(args?.submit)) return "submit"
	return METHOD_SOUNDS.get(String(method).split(".").pop()) || ""
}

/** Plays a Desk sound unless the user muted sounds; browser autoplay blocks fail silently. */
export function playSound(name) {
	try {
		const boot = window.frappe?.boot
		if (!name || boot?.user?.mute_sounds) return
		const sound = (boot?.sounds || []).find((entry) => entry.name === name)
		if (!sound) return
		const audio = players.get(name) || new Audio(sound.src)
		players.set(name, audio)
		audio.volume = Number(sound.volume ?? 1)
		// One sound per burst, e.g. a bulk submit of many rows.
		if (!audio.paused) return
		audio.play()?.catch?.(() => {})
	} catch {
		// Audio is a nicety; never break the action that succeeded.
	}
}

export function playDocumentSound(method, args) {
	playSound(getDocumentSound(method, args))
}
