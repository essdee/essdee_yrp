<template>
    <div v-if="items.length > 0">
        <div style="display:flex;width:100%; justify-content: space-between;">
            <h4>Report</h4>
            <button v-if="status == 'In Progress'" @click="make_complete()" class="btn btn-success">Complete T&A</button>
        </div>
        <table class="table table-sm table-bordered">
            <tr>
                <th>S.No</th>
                <th>Action</th>
                <th>Department</th>
                <th>Lead Time</th>
                <th>Work Station</th>
                <th>Planned Date</th>
                <th>Freezed Date</th>
                <th>Rescheduled Date</th>
                <th>Actual Date</th>
                <th>Planned Delay</th>
                <th>Rescheduled Delay</th>
                <th>Reason</th>
                <th>Performance</th>
            </tr>
            <tr v-for="(row, index) in items" :key="row.action">
                <td>{{ index + 1 }}</td>
                <td>{{ row.action }}</td>
                <td>{{ row.department }}</td>
                <td>{{ row.lead_time }}</td>
                <td>{{ row.work_station }}</td>
                <td>{{ date_format(row.planned_start_date) }}</td>
                <td>{{ date_format(row.date) }}</td>
                <td>{{ date_format(row.rescheduled_date) }}</td>
                <td :class="{ 'bg-red': row.actual_date && row.rescheduled_date < row.actual_date, 'bg-green': row.actual_date && row.rescheduled_date >= row.actual_date }">
                    {{ date_format(row.actual_date) }}
                </td>
                <td>{{ row.actual_delay }}</td>
                <td>{{ row.date_diff }}</td>
                <td>{{ row.reason }}</td>
                <td>{{ row.performance }}%</td>
            </tr>
        </table>
    </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';

const items = ref([])
const status = ref(null)
const time_and_action = cur_frm.doc.__onload?.time_and_action

onMounted(() => {
    if (!time_and_action) return
    frappe.call({
        method: "essdee_yrp.time_and_action.update.get_update_data",
        args: { time_and_action },
        callback: (r) => {
            items.value = r.message.rows
            status.value = r.message.status
        },
    })
})

function make_complete() {
    frappe.call({
        method: "essdee_yrp.time_and_action.update.complete_time_and_action",
        args: { time_and_action },
        callback: () => cur_frm.reload_doc(),
    })
}

function date_format(date) {
    return date ? String(date).split("-").reverse().join("-") : ""
}
</script>
<style scoped>
.bg-red {
    background-color: #f8d7da;
    color: #721c24;
}
.bg-green {
    background-color: #d4edda;
    color: #155724;
}
</style>
