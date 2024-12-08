# Copyright (c) 2024, Rifat Dzhumagulov and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import json
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

    # Fetch daily appointments
    daily_appointments = frappe.get_all(
        "Car wash appointment",
        filters={"starts_on": ["between", [today_date + " 00:00:00", today_date + " 23:59:59"]]},
        fields=["payment_type", "services_total"]
    )

    daily_stats = {
        "total_cars": len(daily_appointments),
        "cash_payment": {"count": 0, "total": 0},
        "card_payment": {"count": 0, "total": 0},
        "kaspi_payment": {"count": 0, "total": 0}
    }

    # Aggregate daily statistics
    for appointment in daily_appointments:
        if appointment["payment_type"] == "Cash":
            daily_stats["cash_payment"]["count"] += 1
            daily_stats["cash_payment"]["total"] += flt(appointment["services_total"])
        elif appointment["payment_type"] == "Card":
            daily_stats["card_payment"]["count"] += 1
            daily_stats["card_payment"]["total"] += flt(appointment["services_total"])
        elif appointment["payment_type"] == "Kaspi":
            daily_stats["kaspi_payment"]["count"] += 1
            daily_stats["kaspi_payment"]["total"] += flt(appointment["services_total"])

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
    # Assuming 31 days, adjust as needed for the correct month end
    current_month_end = (current_month_start.replace(month=current_month_start.month % 12 + 1) - timedelta(days=1))

    # Convert datetime objects to strings for filtering
    current_month_start_str = current_month_start.strftime('%Y-%m-%d')
    current_month_end_str = current_month_end.strftime('%Y-%m-%d')

#     return [current_month_start, current_month_end, current_month_start_str, current_month_end_str]

    # Fetch monthly appointments
    monthly_appointments = frappe.get_all(
        "Car wash appointment",
        filters={"starts_on": ["between", [current_month_start_str + " 00:00:00", current_month_end_str + " 23:59:59"]]},
        fields=["services_total"]
    )

    return monthly_appointments

    total_income = sum(flt(app["services_total"]) for app in monthly_appointments)
    total_cars_month = len(monthly_appointments)
    average_daily_income = total_income / max(current_month_start.day, 1)  # Avoid divide by zero
    average_cars_per_day = total_cars_month / max(current_month_start.day, 1)
    average_check = total_income / total_cars_month if total_cars_month > 0 else 0

    return {
        "total_income": total_income,
        "average_daily_income": average_daily_income,
        "total_cars_month": total_cars_month,
        "average_cars_per_day": average_cars_per_day,
        "average_check": average_check
    }
