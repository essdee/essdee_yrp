<template>
    <div>
        <div v-if="items.length">
            <div style="display:flex;width:100%; justify-content: space-between;">
                <h4>Time and Action Summary</h4>
                <button class="btn btn-success" @click="update_work_station()">Update Work Station</button>
            </div>
            <table class="table table-sm table-bordered">
                <tr>
                    <th>T&A</th>
                    <th>Master</th>
                    <th>Next Action</th>
                    <th>Department</th>
                    <th>Planned Date</th>
                    <th>Rescheduled Date</th>
                </tr>
                <tr v-for="row in items" :key="row.time_and_action">
                    <td><a :href="`/app/sd-yrp-time-and-action/${row.time_and_action}`">{{ row.time_and_action }}</a></td>
                    <td>{{ row.master }}</td>
                    <td>{{ row.action }}</td>
                    <td>{{ row.department }}</td>
                    <td>{{ date_format(row.date) }}</td>
                    <td>{{ date_format(row.rescheduled_date) }}</td>
                </tr>
            </table>
        </div>
    </div>
</template>
<script setup>
import { ref, createApp } from 'vue';
import WorkStation from '../Lot/components/WorkStation.vue';

const items = ref([])

function load_data(rows) {
    items.value = rows || []
}

async function get_data() {
    return { items: items.value, changed: false }
}

function date_format(date) {
    return date ? String(date).split("-").reverse().join("-") : ""
}

function update_work_station() {
    frappe.call({
        method: "essdee_yrp.time_and_action.work_station.get_work_stations",
        args: { time_and_action: items.value[0].time_and_action },
        callback: async function (r) {
            const dialog = new frappe.ui.Dialog({
                size: "extra-large",
                title: __("Update Work Station"),
                fields: [{ fieldname: "html_field", fieldtype: "HTML" }],
                primary_action_label: __("Update"),
                primary_action: () => {
                    dialog.hide()
                    frappe.call({
                        method: "essdee_yrp.time_and_action.work_station.update_t_and_a_ws",
                        args: { datas: editor.get_items() },
                        callback: () => cur_frm.reload_doc(),
                    })
                },
            })
            dialog.fields_dict.html_field.$wrapper.empty()
            const editor = createApp(WorkStation).mount(dialog.fields_dict.html_field.$wrapper[0])
            await editor.load_data(r.message, "update")
            dialog.show()
            editor.set_attributes()
        },
    })
}

defineExpose({
    load_data,
    get_data,
})
</script>
