frappe.views.calendar['Car wash appointment'] = {
    field_map: {
        start: 'starts_on',
        end: 'ends_on',
        id: 'name',
        allDay: 'all_day',
        title: 'heading',
        status: 'workflow_state',
        color: 'color'
    },
    style_map: {
        Public: 'success',
        Private: 'info'
    },
    order_by: 'ends_on',
    get_events_method: 'frappe.desk.doctype.event.event.get_events'
}
