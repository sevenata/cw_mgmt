# car_wash_management/api.py

import frappe
from frappe import _

from car_wash_management.car_wash_management.doctype.car_wash_appointment.car_wash_appointment_manager import CarWashAppointmentManager

# http://localhost:8001/api/method/car_wash_management.api.get_working_hours?wash_id=8213lrjkg7
@frappe.whitelist()
def get_working_hours(wash_id):
	if not wash_id:
		frappe.throw(_("Doc ID is required"))

	manager = CarWashAppointmentManager(wash_id)
	hours = manager.get_working_hours()

	return hours

# http://localhost:8001/api/method/car_wash_management.api.get_time_intervals?wash_id=8213lrjkg7
@frappe.whitelist()
def get_time_intervals(wash_id, day_of_week):
	if not wash_id:
		frappe.throw(_("Doc ID is required"))

	if not day_of_week:
		frappe.throw(_("Day of week is required"))

	manager = CarWashAppointmentManager(wash_id)
	items = manager.get_time_intervals(day_of_week=day_of_week)

	return items


@frappe.whitelist()
def get_appointments(wash_id):
	if not wash_id:
		frappe.throw(_("Doc ID is required"))

	manager = CarWashAppointmentManager(wash_id)
	items = manager.get_appointments()

	return items

# http://localhost:8001/api/method/car_wash_management.api.get_free_slots?wash_id=8213lrjkg7
@frappe.whitelist()
def get_free_slots(wash_id):
	if not wash_id:
		frappe.throw(_("Doc ID is required"))

	manager = CarWashAppointmentManager(wash_id)
	items = manager.get_free_slots()

	return items

@frappe.whitelist()
def get_car_wash_services_with_prices():
    # Fetch all Car wash service records
    services = frappe.get_all(
        "Car wash service",
        fields=["*"],  # Fetch all fields
        filters={"is_deleted": 0}  # Optional: Exclude deleted services
    )

    for service in services:
        # Fetch related prices from Car wash service price
        prices = frappe.get_all(
            "Car wash service price",
            fields=["price", "body_type"],
            filters={"base_service": service["name"]}
        )
        # Add prices field to each service
        service["prices"] = prices

    return services
