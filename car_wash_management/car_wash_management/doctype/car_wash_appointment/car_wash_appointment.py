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
			SELECT MAX(CAST(num AS UNSIGNED)) FROM `tabCar wash appointment`
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
		"payment_received_on",
		"out_of_turn",
		"out_of_turn_reason"
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
		try:
			selected_date = str(getdate(date))
			start_date = selected_date + " 00:00:00"
			end_date = selected_date + " 23:59:59"
		except ValueError:
			frappe.throw("Invalid date format. Please use 'YYYY-MM-DD'.")
	elif start_date and end_date:
		try:
			start_date = str(getdate(start_date)) + " 00:00:00"
			end_date = str(getdate(end_date)) + " 23:59:59"
		except ValueError:
			frappe.throw("Invalid date range format. Please use 'YYYY-MM-DD'.")
	else:
		today_date = today()
		start_date = today_date + " 00:00:00"
		end_date = today_date + " 23:59:59"

	# Fetch appointments within the specified date range.
	# Also fetch "custom_payment_method" if available.
	appointments = frappe.get_all(
		"Car wash appointment",
		filters={
			"payment_received_on": ["between", [start_date, end_date]],
			"is_deleted": 0,
			"payment_status": "Paid",
			"car_wash": car_wash,
		},
		fields=["name", "payment_type", "services_total", "custom_payment_method"],
	)

	# Initialize stats with standard payment types and container for custom payments.
	stats = {
		"total_cars": len(appointments),
		"total_income": 0,
		"cash_payment": {"count": 0, "total": 0},
		"card_payment": {"count": 0, "total": 0},
		"kaspi_payment": {"count": 0, "total": 0},
		"contract_payment": {"count": 0, "total": 0},
		"custom_payments": {}  # Custom payments keyed by custom payment method "name"
	}

	# Pre-load available custom payment methods for the given car wash (if any) using "name" as key.
	custom_payment_filters = {"is_deleted": 0, "is_disabled": 0}
	if car_wash:
		custom_payment_filters["car_wash"] = car_wash

	custom_payment_methods = frappe.get_all(
		"Car wash custom payment method",
		filters=custom_payment_filters,
		fields=["name"]
	)
	for custom in custom_payment_methods:
		stats["custom_payments"][custom["name"]] = {"count": 0, "total": 0}

	standard_payments = ["Cash", "Card", "Kaspi", "Contract"]

	# Aggregate statistics.
	for appointment in appointments:
		stats["total_income"] += flt(appointment["services_total"])
		if appointment["payment_type"] == "Mixed":
			# Fetch child records for mixed payments; also include "custom_payment_method" if provided.
			mixed_payments = frappe.get_all(
				"Car wash mixed payment",
				filters={"parent": appointment["name"]},
				fields=["payment_type", "amount", "custom_payment_method"]
			)
			for payment in mixed_payments:
				if payment["payment_type"] in standard_payments:
					if payment["payment_type"] == "Cash":
						stats["cash_payment"]["count"] += 1
						stats["cash_payment"]["total"] += flt(payment["amount"])
					elif payment["payment_type"] == "Card":
						stats["card_payment"]["count"] += 1
						stats["card_payment"]["total"] += flt(payment["amount"])
					elif payment["payment_type"] == "Kaspi":
						stats["kaspi_payment"]["count"] += 1
						stats["kaspi_payment"]["total"] += flt(payment["amount"])
					elif payment["payment_type"] == "Contract":
						stats["contract_payment"]["count"] += 1
						stats["contract_payment"]["total"] += flt(payment["amount"])
				else:
					# Use the custom_payment_method field if available; fallback to payment_type.
					custom_method = payment.get("custom_payment_method") or payment["payment_type"]
					if custom_method not in stats["custom_payments"]:
						stats["custom_payments"][custom_method] = {"count": 0, "total": 0}
					stats["custom_payments"][custom_method]["count"] += 1
					stats["custom_payments"][custom_method]["total"] += flt(payment["amount"])
		else:
			if appointment["payment_type"] in standard_payments:
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
			else:
				# For non-mixed custom payments, use the custom_payment_method field if available.
				custom_method = appointment.get("custom_payment_method") or appointment["payment_type"]
				if custom_method not in stats["custom_payments"]:
					stats["custom_payments"][custom_method] = {"count": 0, "total": 0}
				stats["custom_payments"][custom_method]["count"] += 1
				stats["custom_payments"][custom_method]["total"] += flt(appointment["services_total"])

	# Additional statistics for multi-day ranges.
	try:
		range_start_date = getdate(start_date.split(" ")[0])
		range_end_date = getdate(end_date.split(" ")[0])
		num_days = (range_end_date - range_start_date).days + 1

		if num_days > 1:
			stats["average_daily_income"] = stats["total_income"] / num_days if num_days > 0 else 0
			stats["average_cars_per_day"] = stats["total_cars"] / num_days if num_days > 0 else 0
			stats["average_check"] = stats["total_income"] / stats["total_cars"] if stats["total_cars"] > 0 else 0
	except ValueError:
		pass

	return stats


@frappe.whitelist()
def export_appointments_to_excel(selected_date=None, start_date=None, end_date=None, car_wash=None):
	"""
	Generate an Excel file in SpreadsheetML format for a given date or a time period and return it for download.

	Args:
		selected_date (str, optional): The date in "YYYY-MM-DD" format to filter appointments (used if time period not provided).
		start_date (str, optional): The start date in "YYYY-MM-DD" format for the time period.
		end_date (str, optional): The end date in "YYYY-MM-DD" format for the time period.
		car_wash (str, optional): Filter appointments by a specific car wash.
	"""
	from io import BytesIO
	from frappe.utils import getdate

	# Determine whether to use a time period or a single selected date.
	if start_date and end_date:
		# Validate the provided time period dates.
		try:
			getdate(start_date)
			getdate(end_date)
		except ValueError:
			frappe.throw("Invalid date format for start_date or end_date. Please provide valid 'YYYY-MM-DD' dates.")
		appointments = get_appointments_by_time_period(start_date, end_date, car_wash)
		date_info = f"{start_date}_to_{end_date}"
	elif selected_date:
		# Validate the provided selected_date.
		try:
			getdate(selected_date)
		except ValueError:
			frappe.throw("Invalid date format for selected_date. Please provide a valid 'YYYY-MM-DD' format.")
		appointments = get_appointments_by_date(selected_date, car_wash)
		date_info = selected_date
	else:
		frappe.throw("Please provide either selected_date or both start_date and end_date in 'YYYY-MM-DD' format.")

	if not appointments:
		frappe.throw(f"No appointments found for the given period ({date_info}).")

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
		"payment_received_on": "Дата оплаты",
		"out_of_turn": "Без очереди",
		"out_of_turn_reason": "Почему без очереди"
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

			cell_type = "Number" if isinstance(value, (int, float)) else "String"
			output.write(f'<Cell><Data ss:Type="{cell_type}">{value}</Data></Cell>\n'.encode('utf-8'))
		output.write(b"</Row>\n")

	# Close XML structure
	output.write(b"</Table>\n</Worksheet>\n</Workbook>\n")

	# Prepare the response
	frappe.response["type"] = "binary"
	frappe.response["filename"] = f"Car_Wash_Appointments_{date_info}.xls"
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



@frappe.whitelist()
def get_appointments_by_time_period(start_date=None, end_date=None, car_wash=None):
	"""
	Extracts Car Wash Appointment records between the given start and end dates.

	Args:
		start_date (str): The start date in "YYYY-MM-DD" format.
		end_date (str): The end date in "YYYY-MM-DD" format.
		car_wash (str, optional): Filter appointments by a specific car wash.

	Returns:
		list: A list of appointments with the specified fields.
	"""
	from frappe.utils import getdate

	if not start_date or not end_date:
		frappe.throw("Please provide both start_date and end_date in 'YYYY-MM-DD' format.")

	# Validate the date formats
	try:
		getdate(start_date)
		getdate(end_date)
	except ValueError:
		frappe.throw("Invalid date format. Please provide valid 'YYYY-MM-DD' dates for both start_date and end_date.")

	# Define the filters. Include car_wash filter only if provided.
	filters = {
		"payment_received_on": ["between", [f"{start_date} 00:00:00", f"{end_date} 23:59:59"]],
		"is_deleted": 0,
		"payment_status": "Paid"
	}
	if car_wash:
		filters["car_wash"] = car_wash

	# List of fields to fetch
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
		"out_of_turn",
		"out_of_turn_reason"
	]

	# Query the database for appointments in the given time period
	appointments = frappe.get_all(
		"Car wash appointment",
		filters=filters,
		fields=fields
	)

	return appointments

@frappe.whitelist()
def export_workers_to_excel(selected_date=None, car_wash=None):
	"""
	Generate an Excel file that contains the workers' provided services in SpreadsheetML format for the selected date and return for download.
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

	# Filter out rows where box_title is "Магазин"
	appointments = [appt for appt in appointments if appt.get("box_title") != "Магазин"]

	if not appointments:
		frappe.throw(f"No appointments found for the date {selected_date}.")

	# Column translations
	COLUMN_TRANSLATIONS = {
		"car_wash_worker_name": "Работник автомойки",
		"name": "Номер заявки",
		"num": "Номер",
		"box_title": "Бокс",
		"work_started_on": "Начало работы",
		"services_total": "Сумма услуг",
		"car_make_name": "Марка автомобиля",
		"car_license_plate": "Номер автомобиля",
		"car_body_type": "Тип кузова"
	}

	CAR_BODY_TYPE_TRANSLATIONS = {
		"Passenger": "Седан",
		"Minbus": "Микроавтобус",
		"LargeSUV": "Большой джип",
		"Jeep": "Джип",
		"Minivan": "Минивэн",
		"CompactSUV": "Кроссовер",
		"Sedan": "Представительский класс"
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

			if header ==  "car_body_type":
				value = CAR_BODY_TYPE_TRANSLATIONS.get(value, value)

			if header == "work_started_on":
				cell_type = "Time"
			elif isinstance(value, (int, float)):
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
	frappe.response["filename"] = f"Car_Wash_Workers_{selected_date}.xls"
	frappe.response["filecontent"] = output.getvalue()
	frappe.response["doctype"] = None  # No need to attach to Frappe's file system

	# Close the output buffer
	output.close()

@frappe.whitelist()
def export_total_services_to_xls(from_date, to_date, car_wash):
	"""
	Generate an Excel report summarizing worker earnings over a specified date range.
	"""
	from io import BytesIO
	from frappe.utils import getdate, add_days

	if not from_date or not to_date:
		frappe.throw("Please provide both from_date and to_date in 'YYYY-MM-DD' format.")

	# Validate date format
	try:
		from_date = getdate(from_date)
		to_date = getdate(to_date)
	except ValueError:
		frappe.throw("Invalid date format. Please provide valid 'YYYY-MM-DD' values.")

	if from_date > to_date:
		frappe.throw("from_date cannot be later than to_date.")

	date_list = []

	# Step 1: Build full date list first
	current_date = from_date
	while current_date <= to_date:
		date_list.append(str(current_date))
		current_date = add_days(current_date, 1)

	# Step 2: Initialize empty earnings dict
	worker_earnings = {}

	# Step 3: Loop through each date and fill earnings
	for date_str in date_list:
		appointments = get_appointments_by_date(date_str, car_wash)

		for appt in appointments:
			worker = appt.get("car_wash_worker_name", "Unknown")
			earnings = appt.get("services_total", 0)

			if worker not in worker_earnings:
				# Ensure we initialize with all dates
				worker_earnings[worker] = {date: 0 for date in date_list}

			worker_earnings[worker][date_str] += earnings

	# Create an in-memory Excel file
	output = BytesIO()
	output.write(b'<?xml version="1.0"?>\n')
	output.write(b'<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
				b'xmlns:o="urn:schemas-microsoft-com:office:office" '
				b'xmlns:x="urn:schemas-microsoft-com:office:excel" '
				b'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">\n')
	output.write(b'<Worksheet ss:Name="Worker Earning">\n<Table>\n')

	# Write title row
	output.write(b"<Row>\n")
	output.write(b'<Cell/>')
	output.write(f'<Cell ss:MergeAcross="5">Расчёт зарплаты за период {str(from_date)}-{str(to_date)}<Data ss:Type="String"></Data></Cell>\n'.encode('utf-8'))
	output.write(b"</Row>\n")

	# Write header row
	headers = ["#", "Работник"] + date_list + ["ИТОГО ОБОРОТ ОМУ", "% за период", "Подпись"]
	output.write(b"<Row>\n")
	for header in headers:
		output.write(f'<Cell><Data ss:Type="String">{header}</Data></Cell>\n'.encode('utf-8'))
	output.write(b"</Row>\n")

	current_row = 3  # Initializing and starting row count
	current_col = 1  # Initializing column count
	for worker, earnings in worker_earnings.items():
		output.write(b"<Row>\n")
		output.write(f'<Cell><Data ss:Type="Number">{current_row - 2}</Data></Cell>\n'.encode('utf-8'))
		output.write(f'<Cell><Data ss:Type="String">{worker}</Data></Cell>\n'.encode('utf-8'))

		current_col = 3  # Starting column count
		for date in date_list:
			value = earnings.get(date, 0)
			output.write(f'<Cell><Data ss:Type="Number">{value}</Data></Cell>\n'.encode('utf-8'))
			current_col += 1

		output.write(f'<Cell ss:Formula="=SUM(R{current_row}C3:R{current_row}C{current_col-1})"><Data ss:Type="Number">0</Data></Cell>\n'.encode('utf-8'))
		output.write(f'<Cell><Data ss:Type="Number"></Data></Cell>\n'.encode('utf-8'))  # Empty Percentage cell
		output.write(b'<Cell><Data ss:Type="String"></Data></Cell>\n')  # Empty Signature cell
		output.write(b"</Row>\n")
		current_row += 1

	output.write(b"<Row>\n")
	output.write(b'<Cell/>')
	output.write(f'<Cell><Data ss:Type="String">ИТОГО</Data></Cell>\n'.encode('utf-8'))

	current_col = 3  # Starting column count
	for i in range(len(date_list) + 1):
		output.write(f'<Cell ss:Formula="=SUM(R3C{current_col}:R{current_row-1}C{current_col})"><Data ss:Type="Number">0</Data></Cell>\n'.encode('utf-8'))
		current_col += 1

	output.write(b"</Row>\n")

	# Close XML structure
	output.write(b"</Table>\n</Worksheet>\n</Workbook>\n")

	# Prepare the response
	frappe.response["type"] = "binary"
	frappe.response["filename"] = f"Периодный_Расчет_{from_date}_-_{to_date}.xls"
	frappe.response["filecontent"] = output.getvalue()
	frappe.response["doctype"] = None  # No need to attach to Frappe's file system

	# Close the output buffer
	output.close()
