# Copyright (c) 2024, Rifat Dzhumagulov and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today, getdate
from datetime import datetime

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

# http://localhost:8000/api/method/car_wash_management.car_wash_management.doctype.car_wash_service.car_wash_service.get_services_statistics
@frappe.whitelist()
def get_services_statistics():
    """
    Fetch daily and monthly service statistics.
    """
    # Today's date
    today_date = today()

    # Start and end of the current month
    current_month_start = datetime.today().replace(day=1).strftime('%Y-%m-%d')
    current_month_end = datetime.today().strftime('%Y-%m-%d')

    # Helper function to aggregate service statistics
    def aggregate_service_stats(start_date, end_date):
        # Fetch services within the given date range
        services = frappe.get_all(
            "Car wash appointment service",
            filters={
                "creation": ["between", [start_date + " 00:00:00", end_date + " 23:59:59"]]
            },
            fields=["service_name", "price"]
        )

        # Aggregate services by service name
        service_stats = {}
        for service in services:
            if service["service_name"] not in service_stats:
                service_stats[service["service_name"]] = {"count": 0, "total": 0}
            service_stats[service["service_name"]]["count"] += 1
            service_stats[service["service_name"]]["total"] += float(service["price"])

        return service_stats

    # Get daily and monthly statistics
    daily_stats = aggregate_service_stats(today_date, today_date)
    monthly_stats = aggregate_service_stats(current_month_start, current_month_end)

    return {
        "daily_stats": daily_stats,
        "monthly_stats": monthly_stats
    }
