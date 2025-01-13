# Copyright (c) 2024, Rifat Dzhumagulov and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import frappe
from frappe.utils import flt, cint, today, add_days, getdate
from datetime import datetime, timedelta
from io import StringIO, BytesIO
import csv

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
        filters={"starts_on": ["between", [today_date + " 00:00:00", today_date + " 23:59:59"]], "payment_status": "Paid", "car_wash": car_wash},
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
        filters={"starts_on": ["between", [current_month_start_str + " 00:00:00", current_month_end_str + " 23:59:59"]], "payment_status": "Paid", "car_wash": car_wash},
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
            filters={"starts_on": ["between", [day_start, day_end]], "payment_status": "Paid", "car_wash": car_wash},
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

@frappe.whitelist()
def get_appointments_by_date(selected_date=None):
    """
    Extracts Car Wash Appointment records for the selected date.

    Args:
    selected_date (str): The date in "YYYY-MM-DD" format to filter appointments.

    Returns:
    list: A list of appointments with the specified fields.
    """
    if not selected_date:
        frappe.throw("Please provide a selected_date in 'YYYY-MM-DD' format.")

    # Validate the date format
    try:
        getdate(selected_date)
    except ValueError:
        frappe.throw("Invalid date format. Please provide a valid 'YYYY-MM-DD' format.")

    # Define the filters
    filters = {
        "starts_on": ["between", [f"{selected_date} 00:00:00", f"{selected_date} 23:59:59"]],
        "is_deleted": 0,
        "payment_status": "Paid"
    }

    # Fetch the required fields
    fields = [
        "name",
        "box_title",
        "work_started_on",
        "car_wash_worker_name",
        "services_total",
        "car_make_name",
        "car_model_name",
        "car_license_plate",
        "car_body_type",
        "payment_type",
        "payment_status"
    ]

    # Query the database
    appointments = frappe.get_all(
        "Car wash appointment",
        filters=filters,
        fields=fields
    )

    return appointments

@frappe.whitelist()
def export_appointments_to_csv(selected_date=None):
    """
    Extract Car Wash Appointments for a selected date and directly return a CSV file for download.
    """
    if not selected_date:
        frappe.throw("Please provide a selected_date in 'YYYY-MM-DD' format.")

    # Validate the date format
    try:
        getdate(selected_date)
    except ValueError:
        frappe.throw("Invalid date format. Please provide a valid 'YYYY-MM-DD' format.")

    # Fetch appointments using the get_appointments_by_date logic
    appointments = get_appointments_by_date(selected_date)

    if not appointments:
        frappe.throw(f"No appointments found for the date {selected_date}.")

    # Use StringIO to generate CSV in memory
    output = StringIO()
    writer = csv.writer(output)

    # Write headers
    headers = list(appointments[0].keys())
    writer.writerow(headers)

    # Write data rows
    for appointment in appointments:
        writer.writerow([appointment.get(header, "") for header in headers])

    # Set the response headers to indicate a file download
    frappe.response["type"] = "binary"
    frappe.response["filename"] = f"Car_Wash_Appointments_{selected_date}.csv"
    frappe.response["filecontent"] = output.getvalue()
    frappe.response["doctype"] = None  # No need to attach to Frappe's file system

    # Close the StringIO object
    output.close()

@frappe.whitelist()
def get_car_wash_statistics():
    """
    Fetch car wash statistics for today, a specific date, or a date range.

    Query parameters:
    - `date` (optional): Specific date in 'YYYY-MM-DD' format.
    - `start_date` and `end_date` (optional): Date range in 'YYYY-MM-DD' format.
    - `car_wash` (optional): Filter by car wash name.
    """
    car_wash = frappe.form_dict.get("car_wash")
    date = frappe.form_dict.get("date")
    start_date = frappe.form_dict.get("start_date")
    end_date = frappe.form_dict.get("end_date")

    # Determine the date range
    if date:
        # Use a single day (midnight to midnight)
        try:
            selected_date = str(getdate(date))
            start_date = selected_date + " 00:00:00"
            end_date = selected_date + " 23:59:59"
        except ValueError:
            frappe.throw("Invalid date format. Please use 'YYYY-MM-DD'.")
    elif start_date and end_date:
        # Use the provided date range
        try:
            start_date = str(getdate(start_date)) + " 00:00:00"
            end_date = str(getdate(end_date)) + " 23:59:59"
        except ValueError:
            frappe.throw("Invalid date range format. Please use 'YYYY-MM-DD'.")
    else:
        # Default to today's date
        today_date = today()
        start_date = today_date + " 00:00:00"
        end_date = today_date + " 23:59:59"

    # Fetch appointments within the specified date range
    appointments = frappe.get_all(
        "Car wash appointment",
        filters={
            "starts_on": ["between", [start_date, end_date]],
            "payment_status": "Paid",
            "car_wash": car_wash,
        },
        fields=["payment_type", "services_total"],
    )

    # Initialize stats
    stats = {
        "total_cars": len(appointments),
        "total_income": 0,
        "cash_payment": {"count": 0, "total": 0},
        "card_payment": {"count": 0, "total": 0},
        "kaspi_payment": {"count": 0, "total": 0},
        "contract_payment": {"count": 0, "total": 0},
    }

    # Aggregate statistics
    for appointment in appointments:
        stats["total_income"] += flt(appointment["services_total"])
        if appointment["payment_type"] == "Cash":
            stats["cash_payment"]["count"] += 1
            stats["cash_payment"]["total"] += flt(appointment["services_total"])
        elif appointment["payment_type"] == "Card":
            stats["card_payment"]["count"] += 1
            stats["card_payment"]["total"] += flt(appointment["services_total"])
        elif appointment["payment_type"] == "Kaspi":
            stats["kaspi_payment"]["count"] += 1
            stats["kaspi_payment"]["total"] += flt(appointment["services_total"])
        elif appointment["payment_type"] == "Contract":
            stats["contract_payment"]["count"] += 1
            stats["contract_payment"]["total"] += flt(appointment["services_total"])

    # Add additional statistics if it's a month-long range
    try:
        range_start_date = getdate(start_date.split(" ")[0])
        range_end_date = getdate(end_date.split(" ")[0])
        num_days = (range_end_date - range_start_date).days + 1

        if num_days > 1:
            stats["average_daily_income"] = (
                stats["total_income"] / num_days if num_days > 0 else 0
            )
            stats["average_cars_per_day"] = (
                stats["total_cars"] / num_days if num_days > 0 else 0
            )
            stats["average_check"] = (
                stats["total_income"] / stats["total_cars"]
                if stats["total_cars"] > 0
                else 0
            )
    except ValueError:
        # Skip additional stats if the date range is invalid
        pass

    return stats

@frappe.whitelist()
def export_appointments_to_excel(selected_date=None):
    """
    Generate an Excel file in SpreadsheetML format for the selected date and return for download.
    """
    from io import BytesIO
    from frappe.utils import getdate

    if not selected_date:
        frappe.throw("Please provide a selected_date in 'YYYY-MM-DD' format.")

    # Validate the date format
    try:
        getdate(selected_date)
    except ValueError:
        frappe.throw("Invalid date format. Please provide a valid 'YYYY-MM-DD' format.")

    # Fetch appointments using the get_appointments_by_date logic
    appointments = get_appointments_by_date(selected_date)

    if not appointments:
        frappe.throw(f"No appointments found for the date {selected_date}.")

    # Create an in-memory buffer for the Excel file
    output = BytesIO()

    # Write SpreadsheetML XML content
    output.write(b'<?xml version="1.0"?>\n')
    output.write(b'<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
                 b'xmlns:o="urn:schemas-microsoft-com:office:office" '
                 b'xmlns:x="urn:schemas-microsoft-com:office:excel" '
                 b'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">\n')
    output.write(b'<Worksheet ss:Name="Appointments">\n<Table>\n')

    # Write headers
    headers = list(appointments[0].keys())
    output.write(b"<Row>\n")
    for header in headers:
        output.write(f'<Cell><Data ss:Type="String">{header}</Data></Cell>\n'.encode('utf-8'))
    output.write(b"</Row>\n")

    # Write data rows
    for appointment in appointments:
        output.write(b"<Row>\n")
        for header in headers:
            value = appointment.get(header, "")
            if isinstance(value, (int, float)):
                cell_type = "Number"
            else:
                cell_type = "String"
            output.write(f'<Cell><Data ss:Type="{cell_type}">{value}</Data></Cell>\n'.encode('utf-8'))
        output.write(b"</Row>\n")

    # Close XML structure
    output.write(b"</Table>\n</Worksheet>\n</Workbook>\n")

    # Prepare the response
    frappe.response["type"] = "binary"
    frappe.response["filename"] = f"Car_Wash_Appointments_{selected_date}.xls"
    frappe.response["filecontent"] = output.getvalue()
    frappe.response["doctype"] = None  # No need to attach to Frappe's file system

    # Close the output buffer
    output.close()
