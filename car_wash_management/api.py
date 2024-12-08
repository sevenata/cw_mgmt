# car_wash_management/api.py

import frappe
import json
import requests
from datetime import datetime, timedelta
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

# OpenWeatherMap API Config
OPENWEATHERMAP_API_URL = "https://api.openweathermap.org/data/2.5/forecast"
CITY_ID = 1526273  # Astana's city ID
API_KEY = "61c936a3c66bc75fe6d12c42d1998738"  # Replace with your actual API key

# http://localhost:8000/api/method/car_wash_management.api.get_weather
@frappe.whitelist()
def get_weather():

	import json

    """
    Fetch weather forecast for Astana and cache it for 6 hours.
    """
    # Cache key for storing weather data
    cache_key = "weather_forecast_astana"

    # Check if cached data exists
    cached_data = frappe.cache().get_value(cache_key)
    if cached_data:
        return frappe.parse_json(cached_data)

    # Fetch weather forecast data from OpenWeatherMap
    try:
        url = f"{OPENWEATHERMAP_API_URL}?id={CITY_ID}&appid={API_KEY}&units=metric"
        response = requests.get(url)
        response.raise_for_status()  # Raise error for non-200 responses
        weather_data = response.json()

        # Serialize weather data to avoid circular references
        serialized_data = json.dumps(weather_data)

        # Save serialized data to cache for 6 hours
        frappe.cache().set_value(cache_key, serialized_data, expires_in_sec=6 * 60 * 60)

        return weather_data
    except requests.exceptions.RequestException as e:
        frappe.throw(f"Error fetching weather data: {str(e)}")
    except ValueError as e:
        frappe.throw(f"Serialization error: {str(e)}")
