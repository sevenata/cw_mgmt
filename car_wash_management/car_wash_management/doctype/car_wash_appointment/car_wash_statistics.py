import frappe
from frappe.utils import getdate, today, flt

def get_statistics(car_wash=None, date=None, start_date=None, end_date=None):
    """
    Получает статистику по мойке автомобилей за указанный день или диапазон дат.

    Параметры:
    - car_wash (str): имя мойки.
    - date (str): конкретная дата (формат 'YYYY-MM-DD').
    - start_date (str): начало периода (формат 'YYYY-MM-DD').
    - end_date (str): конец периода (формат 'YYYY-MM-DD').
    """

    from .car_wash_statistics_helpers import (
        get_date_range,
        get_custom_payment_methods,
        initialize_stats,
        process_standard_payment,
        process_custom_payment,
    )

    start_datetime, end_datetime = get_date_range(date, start_date, end_date)

    appointments = frappe.get_all(
        "Car wash appointment",
        filters={
            "payment_received_on": ["between", [start_datetime, end_datetime]],
            "is_deleted": 0,
            "payment_status": "Paid",
            "car_wash": car_wash,
        },
        fields=["name", "payment_type", "services_total", "custom_payment_method"],
    )

    custom_payment_methods = get_custom_payment_methods(car_wash)
    stats = initialize_stats(appointments, custom_payment_methods)
    standard_payments = ["Cash", "Card", "Kaspi", "Contract"]

    for appointment in appointments:
        stats["total_income"] += flt(appointment["services_total"])
        if appointment["payment_type"] == "Mixed":
            mixed_payments = frappe.get_all(
                "Car wash mixed payment",
                filters={"parent": appointment["name"]},
                fields=["payment_type", "amount", "custom_payment_method"]
            )
            for payment in mixed_payments:
                if payment["payment_type"] in standard_payments:
                    process_standard_payment(stats, payment["payment_type"], payment["amount"])
                else:
                    custom_method = payment.get("custom_payment_method") or payment["payment_type"]
                    process_custom_payment(stats, custom_method, payment["amount"])
        else:
            if appointment["payment_type"] in standard_payments:
                process_standard_payment(stats, appointment["payment_type"], appointment["services_total"])
            else:
                custom_method = appointment.get("custom_payment_method") or appointment["payment_type"]
                process_custom_payment(stats, custom_method, appointment["services_total"])

    try:
        range_start_date = getdate(start_datetime.split(" ")[0])
        range_end_date = getdate(end_datetime.split(" ")[0])
        num_days = (range_end_date - range_start_date).days + 1
        if num_days > 1:
            stats["average_daily_income"] = stats["total_income"] / num_days if num_days > 0 else 0
            stats["average_cars_per_day"] = stats["total_cars"] / num_days if num_days > 0 else 0
            stats["average_check"] = stats["total_income"] / stats["total_cars"] if stats["total_cars"] > 0 else 0
    except ValueError:
        pass

    return stats

@frappe.whitelist()
def get_car_wash_statistics():
    """
    Метод для вызова через API. Берёт параметры из frappe.form_dict и передаёт в бизнес-логику.
    """
    car_wash = frappe.form_dict.get("car_wash")
    date = frappe.form_dict.get("date")
    start_date = frappe.form_dict.get("start_date")
    end_date = frappe.form_dict.get("end_date")

    return get_statistics(
        car_wash=car_wash,
        date=date,
        start_date=start_date,
        end_date=end_date
    )
