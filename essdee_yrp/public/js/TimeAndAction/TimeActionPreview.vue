<template>
    <div ref="root" v-if="Object.keys(items).length > 0">
        <div v-for="item in Object.keys(items)" :key="item">
            <div v-if='items[item].length > 0'>
                <h4 style="line-height:1;">{{item}}</h4>
                <div class="scroll-container2">
                    <table class="inner-table" style="margin-bottom: 20px;">
                        <thead>
                            <tr>
                                <th class="sticky-col col1">Master</th>
                                <th class="sticky-col col2">Start Date</th>
                                <th class="sticky-col col3">Dispatch Date</th>
                                <th class="sticky-col col4">Activity</th>
                                <th v-for="(value,index) in items[item]">{{ value.action }}</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td class="sticky-col col1" rowspan="5">{{ item }}</td>
                                <td class="sticky-col col2" rowspan="5">{{ date_format(start) }}</td>
                                <td class="sticky-col col3" rowspan="5">{{ date_format(items[item][items[item].length - 1]['date']) }}</td>
                            </tr>
                            <tr>
                                <td class="sticky-col col4">Lead Time</td>
                                <td v-for="(value,index) in items[item]">
                                    {{ value.lead_time }}
                                </td>
                            </tr>
                            <tr>
                                <td class="sticky-col col4">Department</td>
                                <td v-for="(value,index) in items[item]">
                                    {{ value.department }}
                                </td>
                            </tr>
                            <tr>
                                <td class="sticky-col col4">Completion Date</td>
                                <td v-for="(value,index) in items[item]">
                                    {{ date_format(value.date) }}
                                </td>
                            </tr>
                            <tr>
                                <td class="sticky-col col4">Work Station</td>
                                <td v-for="(value,index) in items[item]">
                                    <div :ref="(el) => { if (el) cells[value.action] = el }"></div>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</template>
<script setup>
import {ref, nextTick} from 'vue';

let items = ref({})
let start = ref(null)
let cells = {}
let controls = {}
async function load_data(item, start_date){
    items.value = item
    start.value = start_date
    await nextTick()
    for (const rows of Object.values(item)) {
        rows.filter((row) => row.work_station).forEach(make_work_station_control)
    }
}

function make_work_station_control(row){
    controls[row.action] = frappe.ui.form.make_control({
        parent: $(cells[row.action]),
        df: {
            fieldtype: "Link",
            fieldname: "work_station",
            options: "YRP Work Station",
            get_query: () => ({ filters: { action: row.action } }),
        },
        doc: { work_station: row.work_station },
        render_input: true,
    })
    $(cells[row.action]).find(".control-label, .visually-hidden").remove()
}

function get_work_stations(){
    return Object.fromEntries(Object.entries(controls).map(([action, control]) => [action, control.get_value()]))
}

function date_format(date){
    if(date){
        let arr = date.split("-")
        return arr[2]+"-"+arr[1]+"-"+arr[0]
    }
}

defineExpose({
    load_data,
    get_work_stations,
})
</script>

<style scoped>

.scroll-container2 {
    width: 100%;
    max-height: 700px;
    overflow: auto;
    position: relative;
}

.sticky-col {
    border: 1px solid black;
    position: sticky;
    background: white;
    z-index: 1;
    border-right: 1px solid black;
    box-shadow: 2px 0 5px -2px black;
}

.inner-table thead {
    position: sticky;
    top: 0;
    z-index: 5;
    background: white;
}

.inner-table {
    min-width: 3200px;
}

.inner-table thead th.sticky-col {
  position: sticky;
  top: 0;
  z-index: 5;
  background: white;
}

.inner-table th, .inner-table td, .inner-table thead, .inner-table tbody{
    text-align: center;
    word-wrap: break-word;
    border: 1px solid black;
}

.inner-table tbody tr:nth-child(odd) td {
  background-color: #f9f9f9; /* light gray */
}

.inner-table tbody tr:nth-child(even) td {
  background-color: #ffffff; /* white */
}

.inner-table tr{
    border: 1px solid black;
}

.inner-table th{
    background-color: #D3D3D3;
}

.col1 { left: 0;     box-shadow: inset 0 0 0 0.05rem black; width: 60px;}
.col2 { left: 60px;  box-shadow: inset 0 0 0 0.05rem black; width: 120px;}
.col3 { left: 180px; box-shadow: inset 0 0 0 0.05rem black; width: 120px;}
.col4 { left: 300px; box-shadow: inset 0 0 0 0.05rem black; width: 100px;}

</style>
