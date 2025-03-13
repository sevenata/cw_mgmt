from frappe.model.document import Document
import frappe
from frappe.utils import flt, cint, today, add_days, getdate, now_datetime, add_to_date
from datetime import datetime, timedelta
from io import StringIO, BytesIO
from ..car_wash_booking.car_wash_booking import get_booking_price_and_duration
import csv

class Carwashappointment(Document):
	def before_insert(self):
		if not self.car_wash:
			frappe.throw("Car Wash is required")

		max_num = frappe.db.sql(
			"""
            SELECT CAST(MAX(num) AS SIGNED) FROM `tabCar wash appointment`
            WHERE DATE(creation) = %s AND car_wash = %s
            """,
			(today(), self.car_wash),
		)

		self.num = (max_num[0][0] or 0) + 1

		if self.booking:
			booking_doc = frappe.get_doc("Car wash booking", self.booking)
			if booking_doc.payment_status == "Paid":
				self.payment_status = "Paid"
				self.payment_type = booking_doc.payment_type
				self.payment_received_on = booking_doc.payment_received_on

		if not self.payment_status:
			self.payment_status = "Not paid"

		self.workflow_state = "In progress"
		self.starts_on = now_datetime()
		self.work_started_on = self.starts_on

	def validate(self):
		price_and_duration = get_booking_price_and_duration(self.car_wash, self.car, self.services)
		self.services_total = price_and_duration["total_price"]
		self.duration_total = price_and_duration["total_duration"]
		if self.starts_on and not self.ends_on and self.duration_total:
			self.ends_on = add_to_date(self.starts_on, seconds=self.duration_total)

		if self.payment_status == "Paid" and self.payment_type and not self.payment_received_on:
			self.payment_received_on = now_datetime()


from datetime import datetime, timedelta
import frappe


@frappe.whitelist()
def get_appointments_by_date(selected_date=None, car_wash=None):
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
		"payment_received_on": ["between",
								[f"{selected_date} 00:00:00", f"{selected_date} 23:59:59"]],
		"is_deleted": 0,
		"payment_status": "Paid",
		"car_wash": car_wash
	}

	# Fetch the required fields
	fields = [
		"name",
		"num",
		"box_title",
		"work_started_on",
		"car_wash_worker_name",
		"services_total",
		"car_make_name",
		"car_model_name",
		"car_license_plate",
		"car_body_type",
		"payment_type",
		"payment_status",
		"payment_received_on"
	]

	# Query the database
	appointments = frappe.get_all(
		"Car wash appointment",
		filters=filters,
		fields=fields
	)

	return appointments


@frappe.whitelist()
def export_appointments_to_csv(selected_date=None, car_wash=None):
	"""
    Extract Car Wash Appointments for a selected date and directly return a CSV file for download.
    """
	if not selected_date:
		frappe.throw("Please provide a selected_date in 'YYYY-MM-DD' format.")

	if not car_wash:
		frappe.throw("Please provide a car_wash.")

	# Validate the date format
	try:
		getdate(selected_date)
	except ValueError:
		frappe.throw("Invalid date format. Please provide a valid 'YYYY-MM-DD' format.")

	# Fetch appointments using the get_appointments_by_date logic
	appointments = get_appointments_by_date(selected_date, car_wash)

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
			"payment_received_on": ["between", [start_date, end_date]],
			"is_deleted": 0,
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
def export_appointments_to_excel(selected_date=None, car_wash=None):
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
	appointments = get_appointments_by_date(selected_date, car_wash)

	if not appointments:
		frappe.throw(f"No appointments found for the date {selected_date}.")

	# Column translations
	COLUMN_TRANSLATIONS = {
        "name": "Номер заявки",
        "num": "Номер",
        "box_title": "Бокс",
        "work_started_on": "Начало работы",
        "car_wash_worker_name": "Работник автомойки",
        "services_total": "Сумма услуг",
        "car_make_name": "Марка автомобиля",
        "car_model_name": "Модель автомобиля",
        "car_license_plate": "Номер автомобиля",
        "car_body_type": "Тип кузова",
        "payment_type": "Тип оплаты",
        "payment_status": "Статус оплаты",
        "payment_received_on": "Дата оплаты"
    }

    # Value translations
	PAYMENT_TYPE_TRANSLATIONS = {
        "Paid": "Оплачено",
        "Not paid": "Не оплачено",
        "Cash": "Наличные",
        "Card": "Карта",
        "Kaspi": "Каспи",
        "Contract": "Договор"
    }

	CAR_BODY_TYPE_TRANSLATIONS = {
        "Passenger": "Пассажир",
        "Minbus": "Микроавтобус",
        "LargeSUV": "Большой внедорожник",
        "Jeep": "Джип",
        "Minivan": "Минивэн",
        "CompactSUV": "Компактный внедорожник",
        "Sedan": "Седан"
    }

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
		translated_header = COLUMN_TRANSLATIONS.get(header, header)  # Use Russian names
		output.write(f'<Cell><Data ss:Type="String">{translated_header}</Data></Cell>\n'.encode('utf-8'))
	output.write(b"</Row>\n")

	# Write data rows
	for appointment in appointments:
		output.write(b"<Row>\n")
		for header in headers:
			value = appointment.get(header, "")

			if value is None:
				value = "-"
			
			if header == "payment_type":
				value = PAYMENT_TYPE_TRANSLATIONS.get(value, value)
			elif header == "payment_status":
				value = PAYMENT_TYPE_TRANSLATIONS.get(value, value)
			elif header == "car_body_type":
				value = CAR_BODY_TYPE_TRANSLATIONS.get(value, value)

			if isinstance(value, (int, float)):
				cell_type = "Number"
			else:
				cell_type = "String"
			
			output.write(
				f'<Cell><Data ss:Type="{cell_type}">{value}</Data></Cell>\n'.encode('utf-8'))
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

import frappe
from frappe import _
from frappe.utils import getdate, today

@frappe.whitelist()
def get_revenue_by_day():
    """
    Fetch daily revenue breakdown for a selected month or date range.

    Query parameters:
    - `month` (optional): Specific month in 'YYYY-MM' format.
    - `start_date` and `end_date` (optional): Date range in 'YYYY-MM-DD' format.
    - `car_wash` (optional): Filter by car wash name.
    """
    car_wash = frappe.form_dict.get("car_wash")
    month = frappe.form_dict.get("month")
    start_date = frappe.form_dict.get("start_date")
    end_date = frappe.form_dict.get("end_date")

    if month:
        try:
            start_date = f"{month}-01"
            end_date = frappe.utils.get_last_day(start_date)
        except ValueError:
            frappe.throw("Invalid month format. Please use 'YYYY-MM'.")
    elif start_date and end_date:
        try:
            start_date = str(getdate(start_date))
            end_date = str(getdate(end_date))
        except ValueError:
            frappe.throw("Invalid date range format. Please use 'YYYY-MM-DD'.")
    else:
        frappe.throw("Please provide either a month or a date range.")

    appointments = frappe.get_all(
        "Car wash appointment",
        filters={
            "payment_received_on": ["between", [start_date + " 00:00:00", end_date + " 23:59:59"]],
            "is_deleted": 0,
            "payment_status": "Paid",
            "car_wash": car_wash,
        },
        fields=["payment_received_on", "services_total"],
    )

    revenue_by_day = {}

    for appointment in appointments:
        day = appointment["payment_received_on"].date().isoformat()
        revenue_by_day.setdefault(day, 0)
        revenue_by_day[day] += flt(appointment["services_total"])

    # Sort by date
    sorted_revenue = sorted(revenue_by_day.items())

    return {"revenue_by_day": sorted_revenue}
