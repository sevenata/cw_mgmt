# Copyright (c) 2024, Rifat Dzhumagulov and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Carwashservice(Document):
	pass

# http://localhost:8000/api/method/car_wash_management.car_wash_management.doctype.car_wash_service.car_wash_service.get_services_with_prices
# http://localhost:8000/api/method/car_wash_management.api.get_car_wash_services_with_prices
@frappe.whitelist()
def get_services_with_prices():
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
			fields=["price", "body_type", "name"],
			filters={"base_service": service["name"]}
		)
		# Add prices field to each service
		service["prices"] = prices

	return services
