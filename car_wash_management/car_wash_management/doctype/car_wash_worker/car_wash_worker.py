# Copyright (c) 2024, Rifat and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import frappe
from frappe.utils import today, getdate
from datetime import datetime

class Carwashworker(Document):
	pass

# http://localhost:8000/api/method/car_wash_management.car_wash_management.doctype.car_wash_worker.car_wash_worker.get_worker_daily_stats
@frappe.whitelist()
def get_worker_daily_stats():
    """
    Fetch daily statistics for workers.
    """
    return _get_worker_stats(today_date=today())

# http://localhost:8000/api/method/car_wash_management.car_wash_management.doctype.car_wash_worker.car_wash_worker.get_worker_monthly_stats
@frappe.whitelist()
def get_worker_monthly_stats():
    """
    Fetch monthly statistics for workers.
    """
    current_month_start = datetime.today().replace(day=1).strftime('%Y-%m-%d')
    current_month_end = today()  # Today's date as end of the range
    return _get_worker_stats(start_date=current_month_start, end_date=current_month_end)

# http://localhost:8000/api/method/car_wash_management.car_wash_management.doctype.car_wash_worker.car_wash_worker.get_worker_overall_stats
@frappe.whitelist()
def get_worker_overall_stats():
    """
    Fetch overall statistics for workers.
    """
    return _get_worker_stats()

def _get_worker_stats(start_date=None, end_date=None, today_date=None):
    """
    Internal function to calculate worker statistics.
    """
    # Set default date ranges
    if today_date:
        start_date = end_date = today_date
    if not start_date or not end_date:
        start_date = "1900-01-01"  # Default start date for overall stats
        end_date = today()

    car_wash = frappe.form_dict.get("car_wash")

    # Fetch worker appointments within the specified date range
    appointments = frappe.get_all(
        "Car wash appointment",
        filters={
            "payment_received_on": ["between", [start_date + " 00:00:00", end_date + " 23:59:59"]], 
            "car_wash": car_wash,
            "is_deleted": 0,
            "payment_status": "Paid"
        },
        fields=["car_wash_worker", "car_wash_worker_name", "duration_total", "services_total"]
    )

    # Aggregate stats by worker
    worker_stats = {}
    for appointment in appointments:
        worker = appointment["car_wash_worker"]
        if worker not in worker_stats:
            worker_stats[worker] = {
                "worker_name": appointment["car_wash_worker_name"],
                "total_cars": 0,
                "total_amount": 0,
                "total_time": 0
            }
        worker_stats[worker]["total_cars"] += 1
        worker_stats[worker]["total_amount"] += float(appointment["services_total"] or 0)  # Handle None
        worker_stats[worker]["total_time"] += float(appointment["duration_total"] or 0)  # Handle None

    # Calculate average wash time per car for each worker
    for worker, stats in worker_stats.items():
        stats["average_wash_time"] = (
            stats["total_time"] / stats["total_cars"] if stats["total_cars"] > 0 else 0
        )

    return worker_stats
