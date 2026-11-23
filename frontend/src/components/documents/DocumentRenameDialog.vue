<template>
	<Dialog class="document-rename-dialog erp-dialog--sm" :visible="visible" modal :header="`Rename ${docname}`" :closable="!busy" :dismissable-mask="false" @update:visible="close">
		<form class="document-rename-dialog__form" @submit.prevent="rename">
			<div class="document-rename-dialog__current"><span>Current name</span><strong>{{ docname }}</strong></div>
			<label class="document-rename-dialog__field">
				<span>New Name</span>
				<InputText v-model="newName" autofocus :disabled="busy" aria-label="New Name" />
			</label>
			<label class="document-rename-dialog__merge">
				<Checkbox v-model="merge" binary :disabled="busy" input-id="document-rename-merge" />
				<span>Merge with existing <strong>(This cannot be undone)</strong></span>
			</label>
			<div v-if="busy" class="document-rename-dialog__progress" role="status" aria-live="polite">
				<i class="pi pi-spin pi-spinner" aria-hidden="true" />
				<span>Renaming… updating linked documents. Keep this page open.</span>
			</div>
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
		</form>
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="busy" @click="close(false)" />
			<Button :label="busy ? 'Renaming…' : 'Rename'" icon="pi pi-pencil" :loading="busy" :disabled="!canSubmit" @click="rename" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import { useToast } from "primevue/usetoast"
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { getRenameStatus, renameDoc } from "../../api/frappe.js"
import { webDocumentRoute } from "../../router/webDocumentRoutes.js"
import { RENAME_POLL_MS, documentRenamedToast, renamedLocation, waitForRename } from "../../utils/documentRename.js"

const props = defineProps({
	doctype: { type: String, required: true },
	docname: { type: String, required: true },
	visible: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible"])
const route = useRoute()
const router = useRouter()
const toast = useToast()
const newName = ref(props.docname)
const merge = ref(false)
const busy = ref(false)
const error = ref("")
const canSubmit = computed(() => !busy.value && Boolean(newName.value.trim()) && newName.value.trim() !== props.docname)

watch(() => [props.visible, props.docname], ([visible]) => {
	if (!visible) return
	newName.value = props.docname
	merge.value = false
	error.value = ""
})

function close(visible) {
	if (!busy.value) emit("update:visible", visible)
}

async function rename() {
	if (!canSubmit.value) return
	const { doctype, docname } = props
	const target = newName.value.trim()
	busy.value = true
	error.value = ""
	try {
		const { checked_at: since } = await getRenameStatus(doctype, docname, target)
		const returned = await renameDoc(doctype, docname, target, merge.value)
		// Frappe returns the old name when the rename was queued (Desk's enqueue mode).
		const renamed = returned && returned !== docname
			? returned
			: await waitForRename(doctype, docname, target, since, { fetchStatus: getRenameStatus, interval: RENAME_POLL_MS })
		busy.value = false
		emit("update:visible", false)
		await router.replace(renamedLocation(route, docname, renamed) || webDocumentRoute(doctype, renamed))
		toast.add(documentRenamedToast(doctype, docname, renamed))
	} catch (reason) {
		error.value = reason?.message || "Unable to rename this document."
	} finally {
		busy.value = false
	}
}
</script>

<style scoped>
.document-rename-dialog__form { display: grid; gap: 14px; padding: 4px 0; }
.document-rename-dialog__current, .document-rename-dialog__field { display: grid; gap: 6px; }
.document-rename-dialog__current span, .document-rename-dialog__field span { color: var(--erp-text-secondary); font-size: var(--erp-font-size-min); font-weight: var(--erp-font-weight-semibold); }
.document-rename-dialog__current strong { color: var(--erp-text); overflow-wrap: anywhere; }
.document-rename-dialog__progress { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 8px; background: var(--erp-surface-muted); color: var(--erp-text); font-weight: var(--erp-font-weight-semibold); }
.document-rename-dialog__merge { display: flex; align-items: center; gap: 8px; color: var(--erp-text); font-size: 0.88rem; }
</style>
