# Copyright (c) 2024, Rifat Dzhumagulov and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import frappe
from frappe.utils import flt, cint, today, add_days
from datetime import datetime, timedelta

class Carwashappointment(Document):
	pass
# 	@property
# 	def services_json(self):
# 		return frappe.utils.now_datetime() - self.creation

# 	def before_save(self):
#     		self.services_json = json.dumps(self.as_dict()['services'])
#     		self.save()

# http://localhost:8000/api/method/car_wash_management.car_wash_management.doctype.car_wash_appointment.car_wash_appointment.get_daily_car_wash_statistics
@frappe.whitelist()
def get_daily_car_wash_statistics():
    """
    Fetch daily car wash statistics.
    """
    today_date = today()

    car_wash = frappe.form_dict.get("car_wash")

    # Fetch daily appointments
    daily_appointments = frappe.get_all(
        "Car wash appointment",
        filters={"starts_on": ["between", [today_date + " 00:00:00", today_date + " 23:59:59"]], "workflow_state": "Finished", "car_wash": car_wash},
        fields=["payment_type", "services_total"]
    )

    daily_stats = {
        "total_cars": len(daily_appointments),
        "total_income": 0,
        "cash_payment": {"count": 0, "total": 0},
        "card_payment": {"count": 0, "total": 0},
        "kaspi_payment": {"count": 0, "total": 0},
        "contract_payment": {"count": 0, "total": 0}
    }

    # Aggregate daily statistics
    for appointment in daily_appointments:
        daily_stats["total_income"] += flt(appointment["services_total"])
        if appointment["payment_type"] == "Cash":
            daily_stats["cash_payment"]["count"] += 1
            daily_stats["cash_payment"]["total"] += flt(appointment["services_total"])
        elif appointment["payment_type"] == "Card":
            daily_stats["card_payment"]["count"] += 1
            daily_stats["card_payment"]["total"] += flt(appointment["services_total"])
        elif appointment["payment_type"] == "Kaspi":
            daily_stats["kaspi_payment"]["count"] += 1
            daily_stats["kaspi_payment"]["total"] += flt(appointment["services_total"])
        elif appointment["payment_type"] == "Contract":
            daily_stats["contract_payment"]["count"] += 1
            daily_stats["contract_payment"]["total"] += flt(appointment["services_total"])

    return daily_stats

# http://localhost:8000/api/method/car_wash_management.car_wash_management.doctype.car_wash_appointment.car_wash_appointment.get_monthly_car_wash_statistics
@frappe.whitelist()
def get_monthly_car_wash_statistics():
    """
    Fetch monthly car wash statistics.
    """

    # Get the start of the current month
    current_month_start = datetime.today().replace(day=1)

    # Calculate the end of the current month
    if current_month_start.month == 12:
        # If it's December, next month is January of the next year
        current_month_end = current_month_start.replace(year=current_month_start.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        # Get the start of the next month and subtract one day
        current_month_end = current_month_start.replace(month=current_month_start.month + 1, day=1) - timedelta(days=1)

    # Convert datetime objects to strings for filtering
    current_month_start_str = current_month_start.strftime('%Y-%m-%d')
    current_month_end_str = current_month_end.strftime('%Y-%m-%d')

    car_wash = frappe.form_dict.get("car_wash")

    # Fetch monthly appointments
    monthly_appointments = frappe.get_all(
        "Car wash appointment",
        filters={"starts_on": ["between", [current_month_start_str + " 00:00:00", current_month_end_str + " 23:59:59"]], "workflow_state": "Finished", "car_wash": car_wash},
        fields=["services_total"]
    )

    total_income = sum(flt(app["services_total"]) for app in monthly_appointments)
    total_cars_month = len(monthly_appointments)
    average_daily_income = total_income / max(datetime.today().day, 1)  # Avoid divide by zero
    average_cars_per_day = total_cars_month / max(datetime.today().day, 1)
    average_check = total_income / total_cars_month if total_cars_month > 0 else 0

    return {
        "total_income": total_income,
        "average_daily_income": average_daily_income,
        "total_cars_month": total_cars_month,
        "average_cars_per_day": average_cars_per_day,
        "average_check": average_check
    }

from datetime import datetime, timedelta
import frappe

@frappe.whitelist()
def get_last_7_days_car_wash_statistics():
    """
    Fetch car wash appointment statistics for each of the last 7 days.
    """
    today = datetime.today()
    stats = {}

    car_wash = frappe.form_dict.get("car_wash")

    for i in range(7):
        # Calculate the date for the current day in the loop
        day_date = today - timedelta(days=i)
        day_start = day_date.strftime('%Y-%m-%d') + " 00:00:00"
        day_end = day_date.strftime('%Y-%m-%d') + " 23:59:59"

        # Fetch appointments for the current day
        daily_appointments = frappe.get_all(
            "Car wash appointment",
            filters={"starts_on": ["between", [day_start, day_end]], "workflow_state": "Finished", "car_wash": car_wash},
            fields=["services_total"]
        )

        # Calculate stats for the current day
        total_income = sum(flt(app["services_total"]) for app in daily_appointments)
        total_cars = len(daily_appointments)
        average_check = total_income / total_cars if total_cars > 0 else 0

        # Store stats for the day
        stats[day_date.strftime('%Y-%m-%d')] = {
            "total_income": total_income,
            "total_cars": total_cars,
            "average_check": average_check
        }

    return stats
