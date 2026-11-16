<template>
    <div ref="root" style="padding: 20px;">
        <div class="row pb-4">
            <div class="against-type col-md-2"></div>
            <div class="against-id col-md-3"></div>
            <div class="col-md-7" style="padding-top: 27px;">
                <button class="btn btn-success" @click="load_by_filter()">Show</button>
                <button v-if="data && data.can_revise && !is_edited" class="btn btn-default ml-3" @click="revise()">Revise Dates</button>
                <button v-if="data && data.can_edit_steps && !is_edited" class="btn btn-default ml-3" @click="update_actions()">Update Action</button>
                <button v-if="data && data.can_complete && !is_edited" class="btn btn-success ml-3" @click="complete()">Complete T&A</button>
                <template v-if="is_edited">
                    <span class="indicator-pill no-indicator-dot whitespace-nowrap orange ml-3"><span>Not Saved</span></span>
                    <button class="btn btn-default ml-3" @click="load(data.name)">Discard</button>
                    <button class="btn btn-primary ml-3" @click="save()">Save T&A</button>
                </template>
            </div>
        </div>
        <div v-if="is_edited && delivery_message()" class="alert mb-3" :class="data.delivery_days_moved > 0 ? 'alert-danger' : 'alert-success'">
            {{ delivery_message() }}
        </div>
        <div v-if="data" class="ta-update">
            <div class="ta-summary">
                <div><b>T&A</b> <a :href="`/app/sd-yrp-time-and-action/${data.name}`">{{ data.name }}</a></div>
                <div><b>{{ data.against }}</b> {{ data.against_id }}</div>
                <div><b>Master</b> {{ data.master }}</div>
                <div><b>Item</b> {{ data.item }}</div>
                <div><b>Qty</b> {{ data.qty }}</div>
                <div><b>Start</b> {{ format_date(data.start_date) }}</div>
                <div :class="{ 'text-danger': data.end_date_delay }"><b>Expected End</b> {{ format_date(data.end_date) }}</div>
                <div class="running-delay" :class="running_delay_class()" title="Last action's Planned Date vs its Rescheduled or Actual Date, in working days"><b>Running Delay</b> {{ running_delay() }}</div>
                <div><b>Performance</b> {{ data.performance }}%</div>
                <div><b>Status</b> {{ data.status }}</div>
            </div>
            <div class="scroll-container">
                <table class="inner-table">
                    <thead>
                        <tr>
                            <th class="sticky-col">Activity</th>
                            <th v-for="row in data.rows" :key="row.action" class="action-th" :title="dependency_title(row)">
                                <div>{{ row.action }}</div>
                                <div class="text-muted">{{ row.lead_time }} {{ row.lead_time == 1 ? "Day" : "Days" }} · {{ row.department }}</div>
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td class="sticky-col">Planned Date</td>
                            <td v-for="row in data.rows" :key="row.action">{{ format_date(row.planned_start_date) }}</td>
                        </tr>
                        <tr>
                            <td class="sticky-col">Freezed Date</td>
                            <td v-for="row in data.rows" :key="row.action">{{ format_date(row.date) }}</td>
                        </tr>
                        <tr>
                            <td class="sticky-col" style="cursor: pointer;" @click="show_revisions()">Rescheduled Date ({{ data.revised || 0 }})</td>
                            <td v-for="row in data.rows" :key="row.action">{{ format_date(row.rescheduled_date) }}</td>
                        </tr>
                        <tr>
                            <td class="sticky-col">Actual</td>
                            <td v-for="row in data.rows" :key="row.action" :style="{ backgroundColor: actual_colour(row) }">
                                <div v-if="row.can_enter && can_edit(row)" class="d-flex justify-content-center">
                                    <VueDatePicker :model-value="null" format="dd-MM-yyyy" :teleport="true" :enable-time-picker="false"
                                        auto-apply :input-class-name="'custom-input'" @update:model-value="(value) => set_actual(row, value)" />
                                </div>
                                <div v-else class="d-flex justify-content-center">
                                    <span>{{ format_date(row.actual_date) }}</span>
                                    <span v-if="row.can_remove && can_edit(row)" class="cancel-style ml-2" title="Remove" @click="remove_actual(row)">✖</span>
                                </div>
                            </td>
                        </tr>
                        <tr>
                            <td class="sticky-col">Reason for Delay</td>
                            <td v-for="row in data.rows" :key="row.action">
                                <input v-if="row.actual_date && can_edit(row)" v-model="row.reason" class="form-control form-control-sm"
                                    :class="{ 'needs-reason': is_late(row) && !row.reason }" @change="set_reason(row)" />
                                <span v-else>{{ row.reason }}</span>
                            </td>
                        </tr>
                        <tr>
                            <td class="sticky-col">Performance</td>
                            <td v-for="row in data.rows" :key="row.action">{{ row.performance }}%</td>
                        </tr>
                        <tr>
                            <td class="sticky-col">Delay</td>
                            <td v-for="row in data.rows" :key="row.action">{{ row.date_diff }}</td>
                        </tr>
                        <tr>
                            <td class="sticky-col">Cumulative Actual Delay</td>
                            <td v-for="row in data.rows" :key="row.action">{{ row.actual_delay }}</td>
                        </tr>
                        <tr>
                            <td class="sticky-col">Cumulative Rescheduled Delay</td>
                            <td v-for="row in data.rows" :key="row.action">{{ row.cumulative_delay }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
        <div v-else-if="not_found" class="text-muted">No Time and Action for this {{ not_found }}.</div>
    </div>
</template>

<script setup>
import { ref, onMounted, createApp } from 'vue';
import VueDatePicker from '@vuepic/vue-datepicker';
import '@vuepic/vue-datepicker/dist/main.css'
import TandARescheduledDates from "./TandARescheduledDates.vue";
import { open_update_actions } from "./TandAUpdateActions.js";

const root = ref(null)
const data = ref(null)
const changes = ref({})
const is_edited = ref(false)
const not_found = ref(null)
const sample_doc = ref({})
let against = null
let against_id = null

onMounted(() => {
    const el = root.value
    against = frappe.ui.form.make_control({
        parent: $(el).find(".against-type"),
        df: { fieldname: "against", fieldtype: "Select", label: "Against", options: "SD YRP Lot\nYRP Production Order", default: "SD YRP Lot" },
        doc: sample_doc.value,
        render_input: true,
    })
    against.set_value("SD YRP Lot")
    against_id = frappe.ui.form.make_control({
        parent: $(el).find(".against-id"),
        df: { fieldname: "against_id", fieldtype: "Dynamic Link", label: "Lot / Production Order", options: "against" },
        doc: sample_doc.value,
        render_input: true,
    })
    load_from_route()
})

function load_from_route() {
    const name = frappe.route_options?.time_and_action || new URLSearchParams(window.location.search).get("time_and_action")
    frappe.route_options = null
    if (name) load(name)
}

defineExpose({ load_from_route })

function load_by_filter() {
    if (!against_id.get_value()) {
        frappe.msgprint(__("Select a Lot or Production Order."))
        return
    }
    frappe.call({
        method: "essdee_yrp.time_and_action.update.find_time_and_action",
        args: { against: against.get_value(), against_id: against_id.get_value() },
        callback: (r) => {
            if (r.message) return load(r.message)
            data.value = null
            not_found.value = against.get_value()
        },
    })
}

function load(name) {
    frappe.call({
        method: "essdee_yrp.time_and_action.update.get_update_data",
        args: { time_and_action: name },
        callback: (r) => {
            data.value = r.message
            changes.value = {}
            is_edited.value = false
            not_found.value = null
        },
    })
}

function preview(action, change) {
    const pending = { ...changes.value, [action]: change }
    frappe.call({
        method: "essdee_yrp.time_and_action.update.preview_actual_dates",
        args: { time_and_action: data.value.name, changes: Object.values(pending), modified: data.value.modified },
        callback: (r) => {
            changes.value = pending
            data.value = r.message
            is_edited.value = true
        },
    })
}

function set_actual(row, value) {
    if (!value) return
    preview(row.action, { action: row.action, actual_date: to_iso(value), reason: row.reason || null })
}

function remove_actual(row) {
    preview(row.action, { action: row.action, actual_date: null, reason: null })
}

function set_reason(row) {
    changes.value = { ...changes.value, [row.action]: { action: row.action, actual_date: row.actual_date, reason: row.reason || null } }
    is_edited.value = true
}

function save() {
    if (data.value.delivery_days_moved > 0) {
        frappe.confirm(`${delivery_message()}. ${__("Save anyway?")}`, update_actual_dates)
        return
    }
    update_actual_dates()
}

function delivery_message() {
    const days = data.value?.delivery_days_moved
    if (!days) return ""
    const moves = __("Expected delivery date moves from {0} to {1}", [format_date(data.value.delivery_date_before), format_date(data.value.delivery_date_after)])
    const count = Math.abs(days) === 1 ? __("1 working day") : __("{0} working days", [Math.abs(days)])
    return days > 0 ? `${moves} — ${__("delayed by {0} more", [count])}` : `${moves} — ${__("pulled in by {0}", [count])}`
}

function update_actual_dates() {
    frappe.call({
        method: "essdee_yrp.time_and_action.update.update_actual_dates",
        args: { time_and_action: data.value.name, changes: Object.values(changes.value), modified: data.value.modified },
        freeze: true,
        freeze_message: __("Updating T&A"),
        callback: () => {
            frappe.show_alert({ message: __("T&A saved"), indicator: "green" })
            load(data.value.name)
        },
    })
}

function revise() {
    const last = data.value.rows[data.value.rows.length - 1]
    frappe.prompt(
        { fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
        (values) => frappe.call({
            method: "essdee_yrp.time_and_action.update.revise_dates",
            args: { time_and_action: data.value.name, reason: values.reason },
            callback: () => load(data.value.name),
        }),
        __("Dispatch date changes from {0} to {1}. Revise the dates?", [format_date(last.date), format_date(last.rescheduled_date)]),
        __("Revise"),
    )
}

function update_actions() {
    open_update_actions(data.value, () => load(data.value.name))
}

function running_delay() {
    const days = data.value.delay || 0
    if (!days) return __("On schedule")
    const count = Math.abs(days) === 1 ? __("1 working day") : __("{0} working days", [Math.abs(days)])
    return days < 0 ? __("{0} late", [count]) : __("{0} early", [count])
}

function running_delay_class() {
    const days = data.value.delay || 0
    return days < 0 ? "text-danger" : days > 0 ? "text-success" : "text-muted"
}

function complete() {
    frappe.confirm(__("Complete {0}? Its dates are locked after this.", [data.value.name]), () => {
        frappe.call({
            method: "essdee_yrp.time_and_action.update.complete_time_and_action",
            args: { time_and_action: data.value.name },
            freeze: true,
            callback: () => load(data.value.name),
        })
    })
}

function show_revisions() {
    const details = {}
    for (const row of data.value.rows) {
        details[row.action] = {
            planned: row.planned_start_date,
            freeze_date: row.date,
            rescheduled_dates: data.value.revisions[row.action] || [],
            date_diff: row.date_diff,
            actual_delay: row.actual_delay,
            cumulative_delay: row.cumulative_delay,
            reason: row.reason,
            performance: row.performance,
        }
    }
    const dialog = new frappe.ui.Dialog({
        title: __("Rescheduled Details"),
        size: "extra-large",
        fields: [{ fieldtype: "HTML", fieldname: "rescheduled_details_html" }],
    })
    dialog.show()
    createApp(TandARescheduledDates, { rescheduled_details: details }).mount(dialog.fields_dict.rescheduled_details_html.$wrapper.get(0))
}

function can_edit(row) {
    return data.value.status === "In Progress" && (data.value.is_administrator || data.value.departments.includes(row.department))
}

function is_late(row) {
    return row.actual_date && row.actual_date > row.rescheduled_date
}

function actual_colour(row) {
    if (!row.actual_date) return "white"
    return is_late(row) ? "#FFCCCB" : "#90EE90"
}

function dependency_title(row) {
    const names = Object.keys(row.depends_on || {})
    return names.length ? __("Depends on: {0}", [names.join(", ")]) : __("No dependencies")
}

function to_iso(value) {
    const pad = (number) => String(number).padStart(2, "0")
    return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
}

function format_date(value) {
    return value ? String(value).slice(0, 10).split("-").reverse().join("-") : ""
}
</script>

<style scoped>
.ta-summary {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 24px;
    padding: 10px 0;
}
.running-delay {
    font-size: 15px;
    font-weight: 700;
}
.scroll-container {
    width: 100%;
    max-height: 700px;
    overflow: auto;
}
.inner-table {
    border-collapse: collapse;
}
.inner-table th, .inner-table td {
    text-align: center;
    border: 1px solid var(--border-color, #d1d8dd);
    padding: 4px 6px;
    min-width: 130px;
}
.inner-table thead th {
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--subtle-fg, #f3f3f3);
}
.sticky-col {
    position: sticky;
    left: 0;
    z-index: 1;
    background: white;
    font-weight: 600;
    min-width: 200px;
}
.inner-table thead th.sticky-col {
    z-index: 3;
}
.action-th {
    max-width: 220px;
}
.cancel-style {
    cursor: pointer;
    font-weight: bold;
    color: red;
}
.needs-reason {
    box-shadow: inset 2px 2px 0 red;
}
:deep(.dp__menu) {
    z-index: 9999 !important;
}
:deep(.custom-input) {
    height: 26px;
    font-size: 12px;
    width: 120px;
}
</style>
