// Copyright (c) 2024, Rifat Dzhumagulov and contributors
// For license information, please see license.txt

/**
 * Working with tables
 * Show child tables data in frappe datatable on dialog
 * https://discuss.frappe.io/t/show-child-tables-data-in-frappe-datatable-on-dialog/90369/4
 * @param frm
 */

function setStartsOnDate(frm){
	const starts_on = frm.doc.starts_on
	if(!starts_on){
		frm.set_value('ends_on', null)
		return
	}
	frm.set_value('starts_on', moment(starts_on).format("YYYY-MM-DD HH:mm"))
	const totalDuration = frm.doc.duration_total
	if(totalDuration) {
		const startDate = new Date(starts_on)
		startDate.setTime(startDate.getTime() + 1e3 * totalDuration)
		frm.set_value('ends_on', moment(startDate).format("YYYY-MM-DD HH:mm"))
	}
}

async function refreshNearestAppointments(frm){
	const appointments = await frappe.db.get_list('Car wash appointment', {
		fields: ['starts_on', 'ends_on','customer_name', 'worker_name', 'box_name', 'box_color', 'duration_total', 'workflow_state'],
		filters: {
			car_wash: frm.doc.car_wash,
		}
	})

	$('[data-fieldname="nearest_bookings"]').remove()

	frappe.ui.form.make_control({
		parent: $('[data-fieldname="car_wash_column_break"]'),
		df: {
			fieldname: "nearest_bookings",
			fieldtype: "Table",
			label: "Ближайшие бронирования",
			cannot_add_rows: true,
			in_place_edit: false,
			data: appointments,
			read_only: 1,
			get_data: () => {
				return appointments;
			},
			fields: [{
				fieldtype:"Data",
				fieldname:"customer_name",
				in_list_view: 1,
				label: "Клиент",
				read_only: 1,
			},{
				fieldtype:"Data",
				fieldname:"box_name",
				in_list_view: 1,
				label: "Бокс",
				read_only: 1,
				// hidden: 0
			},{
				fieldtype:"Data",
				fieldname:"worker_name",
				in_list_view: 1,
				label: "Исполнитель",
				read_only: 1,
				// hidden: 0
			},{
				fieldtype:"Datetime",
				fieldname:"starts_on",
				in_list_view: 1,
				label: "Начало",
				read_only: 1,
				// hidden: 0
			},{
				fieldtype:"Duration",
				fieldname:"duration_total",
				in_list_view: 1,
				label: "Продолжительность",
				read_only: 1,
				// hidden: 0
			},{
				fieldtype:"Datetime",
				fieldname:"ends_on",
				in_list_view: 1,
				label: "Окончание",
				read_only: 1,
				// hidden: 0
			}]
		},
		render_input: true,
	})
}

function setFormFieldReadOnly(frm, key, value){
	var field = frm.get_field(key);
	field.$input.prop('readonly', value);
}

function disableBoxField(frm){
	setFormFieldReadOnly(frm, "box", true)
}

function enableBoxField(frm){
	setFormFieldReadOnly(frm, "box", false)
}

function disableWorkerField(frm){
	setFormFieldReadOnly(frm, "worker", true)
}

function enableWorkerField(frm){
	setFormFieldReadOnly(frm, "worker", false)
}

frappe.ui.form.on('Car wash appointment', {
	refresh: function(frm){
		if(frm.is_new()){
			frm.toggle_display("workflow_state", false);
		}
		if(!frm.doc.car_wash) {
			disableBoxField(frm)
			disableWorkerField(frm)
		}
	},
	car_wash: async function(frm, cdt, cdn) {
		if(!frm.doc.car_wash){
			disableBoxField(frm)
			disableWorkerField(frm)
			return
		}
		enableBoxField(frm)
		enableWorkerField(frm)
		frm.set_query("box", function(){
			return {
				"filters": [
					["Car wash box", "car_wash", "=", frm.doc.car_wash],
				]
			}
		});
		frm.set_query("worker", function(){
			return {
				"filters": [
					["Car wash worker", "car_wash", "=", frm.doc.car_wash],
				]
			}
		});

		await refreshNearestAppointments(frm)
	},
	starts_on: function(frm, cdt, cdn) {
		setStartsOnDate(frm)
	},
})

frappe.ui.form.on('Car wash appointment service', {
	service_price: function(frm, cdt, cdn) {
		total_incentive = 0
		duration_total = 0
		$.each(frm.doc.services,  function(i,  d) {
			total_incentive += d.service_price || 0
			duration_total += d.duration || 0
		});
		frm.set_value('services_total', total_incentive)
		frm.set_value('duration_total', duration_total)
		if(frm.doc.starts_on){
			setStartsOnDate(frm)
		}
	},
})
