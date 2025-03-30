# helpers.py
import frappe
from frappe.utils import getdate, today, flt

def get_date_range(date=None, start_date=None, end_date=None):
    try:
        if date:
            selected_date = str(getdate(date))
            return f"{selected_date} 00:00:00", f"{selected_date} 23:59:59"
        elif start_date and end_date:
            return f"{str(getdate(start_date))} 00:00:00", f"{str(getdate(end_date))} 23:59:59"
        else:
            today_date = today()
            return f"{today_date} 00:00:00", f"{today_date} 23:59:59"
    except ValueError:
        frappe.throw("Неверный формат даты. Используйте 'YYYY-MM-DD'.")

def get_custom_payment_methods(car_wash=None):
    filters = {"is_deleted": 0, "is_disabled": 0}
    if car_wash:
        filters["car_wash"] = car_wash
    return frappe.get_all("Car wash custom payment method", filters=filters, fields=["name"])

def initialize_stats(appointments, custom_payment_methods):
    stats = {
        "total_cars": len(appointments),
        "total_income": 0,
        "cash_payment": {"count": 0, "total": 0},
        "card_payment": {"count": 0, "total": 0},
        "kaspi_payment": {"count": 0, "total": 0},
        "contract_payment": {"count": 0, "total": 0},
        "custom_payments": {}
    }
    for custom in custom_payment_methods:
        stats["custom_payments"][custom["name"]] = {"count": 0, "total": 0}
    return stats

def process_standard_payment(stats, payment_type, amount):
    stats_key = f"{payment_type.lower()}_payment"
    if stats_key in stats:
        stats[stats_key]["count"] += 1
        stats[stats_key]["total"] += flt(amount)

def process_custom_payment(stats, custom_method, amount):
    if custom_method not in stats["custom_payments"]:
        stats["custom_payments"][custom_method] = {"count": 0, "total": 0}
    stats["custom_payments"][custom_method]["count"] += 1
    stats["custom_payments"][custom_method]["total"] += flt(amount)
