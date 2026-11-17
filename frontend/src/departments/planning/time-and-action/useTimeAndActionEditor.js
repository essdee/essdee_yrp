import { computed, ref, toRaw } from "vue"

import {
	completeTimeAndAction, getSupplierChips, getUpdateData, previewActualDates, reviseDates, setPlannedSuppliers, updateActualDates,
} from "../../../api/timeAndAction.js"
import { canEditRow, countStatuses, getBlockedBy, getRowStatus, isLate, todayIso } from "./timeAndAction.js"

/** State of one T&A editor: server data, pending changes, per-row server errors; the server validates every date. */
export function useTimeAndActionEditor(name) {
	const base = ref(null)
	const data = ref(null)
	const changes = ref({})
	const rowErrors = ref({})
	const loading = ref(false)
	const busy = ref(false)
	const loadError = ref("")
	const chips = ref({})
	const today = todayIso()

	const baseRows = computed(() => Object.fromEntries((base.value?.rows || []).map((row) => [row.action, row])))
	const rows = computed(() => (data.value?.rows || []).map((row, index) => describeRow(row, index)))
	const nextIndex = computed(() => rows.value.findIndex((row) => row.status === "due" || row.status === "overdue"))
	const counts = computed(() => countStatuses(rows.value.map((row) => row.status)))
	const datedCount = computed(() => rows.value.filter((row) => row.actual_date && !row.error).length)
	const missingReasons = computed(() => rows.value.filter((row) => row.needsReason).length)
	const unsavedCount = computed(() => new Set([...Object.keys(changes.value), ...Object.keys(rowErrors.value)]).size)
	const hasChanges = computed(() => Object.keys(changes.value).length > 0)
	const canSave = computed(() => hasChanges.value && !counts.value.error && !missingReasons.value && !busy.value)

	function describeRow(row, index) {
		const error = rowErrors.value[row.action]
		const old = baseRows.value[row.action] || row
		const status = getRowStatus(row, { hasError: Boolean(error), today })
		const late = !error && isLate(row)
		return {
			...row,
			index,
			error: error?.message || "",
			inputValue: error ? error.actual_date : row.actual_date || "",
			status,
			blockedBy: getBlockedBy(row),
			editable: canEditRow(data.value, row) && status !== "blocked",
			edited: Boolean(changes.value[row.action] || error),
			late,
			needsReason: late && !(row.reason || "").trim(),
			oldRescheduledDate: old.rescheduled_date !== row.rescheduled_date ? old.rescheduled_date : "",
		}
	}

	async function load() {
		loading.value = true
		loadError.value = ""
		try {
			const [payload, supplierChips] = await Promise.all([getUpdateData(name), getSupplierChips(name)])
			base.value = payload
			chips.value = supplierChips
			reset()
		} catch (reason) {
			loadError.value = reason?.message || "Unable to load this Time and Action."
		} finally {
			loading.value = false
		}
	}

	function reset() {
		data.value = structuredClone(toRaw(base.value))
		changes.value = {}
		rowErrors.value = {}
	}

	function isUnchanged(change) {
		const old = baseRows.value[change.action]
		return (old.actual_date || "") === (change.actual_date || "") && (old.reason || "") === (change.reason || "")
	}

	function withChange(change) {
		const pending = { ...changes.value }
		if (isUnchanged(change)) delete pending[change.action]
		else pending[change.action] = change
		return pending
	}

	async function setActual(row, value) {
		if ((value || "") === (row.inputValue || "")) return
		const pending = withChange({ action: row.action, actual_date: value || null, reason: row.reason || null })
		const errors = { ...rowErrors.value }
		delete errors[row.action]
		busy.value = true
		try {
			data.value = Object.keys(pending).length
				? await previewActualDates(name, Object.values(pending), base.value.modified)
				: structuredClone(toRaw(base.value))
			changes.value = pending
		} catch (reason) {
			errors[row.action] = { actual_date: value, message: reason?.message || "Unable to apply this date." }
		} finally {
			rowErrors.value = errors
			busy.value = false
		}
	}

	function setReason(row, reason) {
		const target = data.value.rows.find((item) => item.action === row.action)
		target.reason = reason
		changes.value = withChange({ action: row.action, actual_date: target.actual_date || null, reason: reason || null })
	}

	async function save() {
		await updateActualDates(name, Object.values(changes.value), base.value.modified)
		await load()
	}

	async function complete() {
		if (hasChanges.value) await save()
		await completeTimeAndAction(name)
	}

	/** Planned suppliers save on their own; pending date changes keep working against the new `modified`. */
	async function savePlannedSuppliers(action, suppliers) {
		const result = await setPlannedSuppliers(name, action, suppliers)
		chips.value = result.chips
		base.value.modified = result.modified
		data.value.modified = result.modified
	}

	async function revise(reason) {
		await reviseDates(name, reason)
		await load()
	}

	return {
		data, rows, nextIndex, counts, datedCount, missingReasons, unsavedCount, hasChanges, canSave,
		loading, busy, loadError, today, load, reset, setActual, setReason, save, complete, revise,
		chips, savePlannedSuppliers,
	}
}
