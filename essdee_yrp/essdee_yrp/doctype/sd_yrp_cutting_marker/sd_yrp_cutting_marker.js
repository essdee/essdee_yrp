// Copyright (c) 2024, Essdee and contributors
// For license information, please see license.txt

frappe.ui.form.on("SD YRP Cutting Marker", {
	setup(frm) {
		frm.set_query("cutting_plan", () => {
			return {
				filters: {
					"cp_status": ["!=", "Completed"],
					"docstatus": 1,
				}
			}
		})
		frm.set_query("cutting_order", () => {
			return {
				filters: {
					"docstatus": 1,
					"co_status": ["!=", "Completed"],
				}
			}
		})
	},
	refresh(frm) {
		// Toggle visibility: show one parent, hide the other
		if (frm.doc.cutting_order) {
			frm.set_df_property("cutting_plan", "hidden", 1)
		} else if (frm.doc.cutting_plan) {
			frm.set_df_property("cutting_order", "hidden", 1)
		}

		frm.set_df_property('cutting_marker_ratios','cannot_add_rows',true)
		frm.set_df_property('cutting_marker_ratios','cannot_delete_rows',true)
		$(frm.fields_dict['cutting_marker_ratios_html'].wrapper).html("")
		if(!frm.doc.__islocal){
			frm.marker_ratios = new frappe.production.ui.CuttingMarker($(frm.fields_dict['cutting_marker_ratios_html'].wrapper))
			if( frm.doc.__onload && frm.doc.__onload.marker_detail){
				frm.marker_ratios.load_data(frm.doc.__onload.marker_detail)
			}
			else{
				frm.marker_ratios.load_data([])
			}
		}
	},
	cutting_plan(frm) {
		if (frm.doc.cutting_plan) {
			frm.set_value("cutting_order", "")
			frm.set_df_property("cutting_order", "hidden", 1)
		} else {
			frm.set_df_property("cutting_order", "hidden", 0)
		}
	},
	cutting_order(frm) {
		if (frm.doc.cutting_order) {
			frm.set_value("cutting_plan", "")
			frm.set_df_property("cutting_plan", "hidden", 1)
			// Fetch item from cutting order
			if (frm.doc.cutting_order) {
				frappe.db.get_value("SD YRP Cutting Order", frm.doc.cutting_order, "item").then(r => {
					if (r.message && r.message.item) {
						frm.set_value("item", r.message.item)
					}
				})
			}
		} else {
			frm.set_df_property("cutting_plan", "hidden", 0)
		}
	},
	preview_required_piece_weight(frm) {
		if (frm.doc.docstatus !== 0 || !frm.marker_ratios) return
		frappe.call({
			method: "essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_marker.sd_yrp_cutting_marker.preview_marker_piece_weight",
			args: {
				cutting_plan: frm.doc.cutting_plan,
				cutting_order: frm.doc.cutting_order,
				selected_type: frm.doc.selected_type,
				panels: (frm.doc.calculated_parts || "").split(",").filter(Boolean),
				ratio_items: frm.marker_ratios.get_ratio_items(),
			},
		}).then((r) => {
			const result = r.message || {}
			if (result.weight !== null && result.weight !== undefined) {
				frm.set_value("required_piece_weight", result.weight)
			}
			frm.set_df_property("required_piece_weight", "description", result.message || "")
		})
	},
	validate(frm){
		if(frm.marker_ratios && !frm.doc.__islocal){
			let items = frm.marker_ratios.get_items()
			frm.doc['marker_details'] = items
		}
	}
});
