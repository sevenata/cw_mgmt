# car_wash_management/api.py

import frappe
from frappe import _

# http://localhost:8001/api/method/car_wash_management.api.get_working_hours?box_id=8213lrjkg7
@frappe.whitelist()
def get_working_hours(box_id):
	if not box_id:
		frappe.throw(_("Doc ID is required"))

	box = frappe.get_doc('Car wash box', box_id)
	items = box.get_working_hours()
	return items

# http://localhost:8001/api/method/car_wash_management.api.get_time_intervals?box_id=8213lrjkg7
@frappe.whitelist()
def get_time_intervals(box_id):
	if not box_id:
		frappe.throw(_("Doc ID is required"))

	box = frappe.get_doc('Car wash box', box_id)
	items = box.get_time_intervals()
	return items


@frappe.whitelist()
def get_appointments(box_id):
	if not box_id:
		frappe.throw(_("Doc ID is required"))

	box = frappe.get_doc('Car wash box', box_id)
	items = box.get_appointments()
	return items

# http://localhost:8001/api/method/car_wash_management.api.get_free_slots?box_id=8213lrjkg7
@frappe.whitelist()
def get_free_slots(box_id):
	if not box_id:
		frappe.throw(_("Doc ID is required"))

	box = frappe.get_doc('Car wash box', box_id)
	items = box.get_free_slots()
	return items
