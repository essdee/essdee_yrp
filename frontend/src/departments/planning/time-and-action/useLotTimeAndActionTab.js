import { computed, reactive, ref, toValue, watch } from "vue"

import { createTimeAndActionActions } from "./productionOrderTimeAndAction.js"
import { lotTimeAndActionUpdateRouteName } from "./timeAndActionRoutes.js"
import { useLotTimeAndAction } from "./useProductionOrderTimeAndAction.js"

export const TIME_AND_ACTION_TAB = { key: "time-and-action", label: "Time and Action" }

/** A Lot page's Time and Action tab, header Create T&A and Create dialog; all hidden unless the user can read T&A. */
export function useLotTimeAndActionTab({ lotId, department, activeTab, onChanged }) {
	const { context, error, load } = useLotTimeAndAction(lotId)
	const canRead = computed(() => Boolean(context.value?.can_read))
	const createVisible = ref(false)

	watch([context, activeTab], () => {
		if (context.value && !canRead.value && activeTab.value === TIME_AND_ACTION_TAB.key) activeTab.value = "lot"
	})

	function changed() {
		load()
		onChanged?.()
	}

	return reactive({
		canRead,
		createVisible,
		tabProps: computed(() => ({
			lot: toValue(lotId),
			updateRouteName: lotTimeAndActionUpdateRouteName(department),
			timeAndAction: context.value?.time_and_action || "",
			loadError: error.value,
			canCreate: Boolean(context.value?.can_create),
			createBlockedReason: context.value?.create_blocked_reason || "",
		})),
		dialogProps: computed(() => ({ against: "SD YRP Lot", againstId: toValue(lotId), item: context.value?.item || "", qty: context.value?.qty || 0 })),
		/** `tabs` with the Time and Action tab last, only when the user can read T&A. */
		withTab: (tabs) => [...tabs.filter((tab) => tab.key !== TIME_AND_ACTION_TAB.key), ...(canRead.value ? [TIME_AND_ACTION_TAB] : [])],
		actions: (busy) => createTimeAndActionActions(context.value, { busy, onCreate: () => { createVisible.value = true } }),
		changed,
		created() {
			changed()
			activeTab.value = TIME_AND_ACTION_TAB.key
		},
	})
}
