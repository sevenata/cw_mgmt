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
		"out_of_turn_reason",
		"owner",
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
		"out_of_turn_reason",
		"owner",
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
	cashier_earnings = {}

	# Step 3: Loop through each date and fill earnings
	for date_str in date_list:
		appointments = get_appointments_by_date(date_str, car_wash)

		for appt in appointments:
			worker = appt.get("car_wash_worker_name", "Unknown")
			cashier = appt.get("owner", "Unknown")
			earnings = appt.get("services_total", 0)

			if worker not in worker_earnings:
				# Ensure we initialize with all dates
				worker_earnings[worker] = {date: 0 for date in date_list}
			worker_earnings[worker][date_str] += earnings

			if cashier not in cashier_earnings:
				cashier_earnings[cashier] = {date: 0 for date in date_list}
			cashier_earnings[cashier][date_str] += earnings

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
	output.write(b'<Cell><Data ss:Type="String"></Data></Cell>\n')
	merge_across = str(len(date_list) + 3)
	title = "Расчёт зарплаты за период " + str(from_date) + "-" + str(to_date)
	cell_content = '<Cell ss:MergeAcross="' + merge_across + '"><Data ss:Type="String">' + title + '</Data></Cell>\n'
	output.write(cell_content.encode('utf-8'))
	output.write(b"</Row>\n")

	# Write header row
	headers = ["#", "Работник"] + date_list + ["ИТОГО ОБОРОТ ОМУ", "% за период", "Заработано"]
	output.write(b"<Row>\n")
	for header in headers:
		cell_content = '<Cell><Data ss:Type="String">' + header + '</Data></Cell>\n'
		output.write(cell_content.encode('utf-8'))
	output.write(b"</Row>\n")

	# Write washers section
	output.write(b"<Row>\n")
	output.write(b'<Cell><Data ss:Type="String">\xd0\x9c\xd0\xbe\xd0\xb9\xd1\x89\xd0\xb8\xd0\xba\xd0\xb8</Data></Cell>\n')
	output.write(b"</Row>\n")

	current_row = 4  # Initializing and starting row count
	current_col = 1  # Initializing column count
	for worker, earnings in worker_earnings.items():
		output.write(b"<Row>\n")
		cell_content = '<Cell><Data ss:Type="Number">' + str(current_row - 3) + '</Data></Cell>\n'
		output.write(cell_content.encode('utf-8'))
		# Handle None values for worker name
		worker_name = worker if worker is not None else "Неизвестный мойщик"
		cell_content = '<Cell><Data ss:Type="String">' + worker_name + '</Data></Cell>\n'
		output.write(cell_content.encode('utf-8'))

		current_col = 3  # Starting column count
		for date in date_list:
			value = str(earnings.get(date, 0))
			cell_content = '<Cell><Data ss:Type="Number">' + value + '</Data></Cell>\n'
			output.write(cell_content.encode('utf-8'))
			current_col += 1

		# Calculate total for this row
		row_total = sum(earnings.get(date, 0) for date in date_list)
		output.write(('<Cell><Data ss:Type="Number">{}</Data></Cell>\n'.format(row_total)).encode('utf-8'))
		output.write(b'<Cell><Data ss:Type="String">30%</Data></Cell>\n')
		# Calculate 30% of total earnings
		earned = row_total * 0.3
		output.write(('<Cell><Data ss:Type="Number">{}</Data></Cell>\n'.format(earned)).encode('utf-8'))
		output.write(b"</Row>\n")
		current_row += 1

	# Write cashiers section
	output.write(b"<Row>\n")
	output.write(b'<Cell><Data ss:Type="String">\xd0\x9a\xd0\xb0\xd1\x81\xd1\x81\xd0\xb8\xd1\x80\xd1\x8b</Data></Cell>\n')
	output.write(b"</Row>\n")

	cashier_start_row = current_row
	for cashier, earnings in cashier_earnings.items():
		output.write(b"<Row>\n")
		cell_content = '<Cell><Data ss:Type="Number">' + str(current_row - cashier_start_row + 1) + '</Data></Cell>\n'
		output.write(cell_content.encode('utf-8'))
		# Handle None values for cashier name
		cashier_name = cashier if cashier is not None else "Неизвестный кассир"
		cell_content = '<Cell><Data ss:Type="String">' + cashier_name + '</Data></Cell>\n'
		output.write(cell_content.encode('utf-8'))

		current_col = 3  # Starting column count
		for date in date_list:
			value = str(earnings.get(date, 0))
			cell_content = '<Cell><Data ss:Type="Number">' + value + '</Data></Cell>\n'
			output.write(cell_content.encode('utf-8'))
			current_col += 1

		# Calculate total for this row
		row_total = sum(earnings.get(date, 0) for date in date_list)
		output.write(('<Cell><Data ss:Type="Number">{}</Data></Cell>\n'.format(row_total)).encode('utf-8'))
		output.write(b'<Cell><Data ss:Type="String">10%</Data></Cell>\n')
		# Calculate 10% of total earnings
		earned = row_total * 0.1
		output.write(('<Cell><Data ss:Type="Number">{}</Data></Cell>\n'.format(earned)).encode('utf-8'))
		output.write(b"</Row>\n")
		current_row += 1

	# Write total row
	output.write(b"<Row>\n")
	output.write(b'<Cell><Data ss:Type="String"></Data></Cell>\n')
	output.write(b'<Cell><Data ss:Type="String">\xd0\x98\xd0\xa2\xd0\x9e\xd0\x93\xd0\x9e</Data></Cell>\n')

	current_col = 3  # Starting column count
	for i in range(len(date_list) + 1):
		output.write(('<Cell ss:Formula="=SUM(R4C{}:R{}C{})"><Data ss:Type="Number">0</Data></Cell>\n'.format(current_col, current_row-1, current_col)).encode('utf-8'))
		current_col += 1
	# Add total for earnings column
	output.write(('<Cell ss:Formula="=SUM(R4C{}:R{}C{})"><Data ss:Type="Number">0</Data></Cell>\n'.format(current_col-2, current_row-1, current_col-2)).encode('utf-8'))
	# Calculate total earnings (30% for washers + 10% for cashiers)
	output.write(('<Cell ss:Formula="=SUM(R4C{}:R{}C{})*0.3+SUM(R{}C{}:R{}C{})*0.1"><Data ss:Type="Number">0</Data></Cell>\n'.format(
		current_col-2, cashier_start_row-1, current_col-2,
		cashier_start_row+1, current_col-2, current_row-1, current_col-2
	)).encode('utf-8'))
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


	
import frappe
from io import BytesIO
from frappe.utils import getdate

def _get_appointments(selected_date, start_date, end_date, car_wash):
	"""
	Fetch appointments based on a selected date or a date range.
	Returns a tuple (appointments, date_info) where date_info is used for naming the file.
	"""
	if start_date and end_date:
		try:
			getdate(start_date)
			getdate(end_date)
		except ValueError:
			frappe.throw("Invalid date format for start_date or end_date. Please provide valid 'YYYY-MM-DD' dates.")
		appointments = get_appointments_by_time_period(start_date, end_date, car_wash)
		date_info = f"{start_date}_to_{end_date}"
	elif selected_date:
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
	return appointments, date_info

def _get_appointment_column_translations():
	"""
	Returns a dictionary mapping appointment column keys to Russian translations.
	"""
	return {
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
		"out_of_turn_reason": "Почему без очереди",
		"owner": "Добавил"
	}

def _translate_value(field, value):
	"""
	Translates values for specific fields such as payment types or car body types.
	"""
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

	if field in ["payment_type", "payment_status"]:
		return PAYMENT_TYPE_TRANSLATIONS.get(value, value)
	elif field == "car_body_type":
		return CAR_BODY_TYPE_TRANSLATIONS.get(value, value)
	return value

def _generate_multi_sheet_excel(sheets_data):
	"""
	Generates a multi-sheet Excel file in SpreadsheetML XML format.

	Args:
		sheets_data (dict): Keys are sheet names and values are tuples (headers, rows, translations).

	Returns:
		Binary Excel content.
	"""
	output = BytesIO()
	output.write(b'<?xml version="1.0"?>\n')
	output.write(b'<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" ')
	output.write(b'xmlns:o="urn:schemas-microsoft-com:office:office" ')
	output.write(b'xmlns:x="urn:schemas-microsoft-com:office:excel" ')
	output.write(b'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">\n')

	for sheet_name, (headers, rows, translations) in sheets_data.items():
		output.write(f'<Worksheet ss:Name="{sheet_name}">\n'.encode("utf-8"))
		output.write(b'<Table>\n')
		# Write header row with translated column names
		output.write(b"<Row>\n")
		for header in headers:
			translated = translations.get(header, header)
			output.write(f'<Cell><Data ss:Type="String">{translated}</Data></Cell>\n'.encode("utf-8"))
		output.write(b"</Row>\n")
		# Write data rows
		for row in rows:
			output.write(b"<Row>\n")
			for header in headers:
				value = row.get(header, "-")
				if value is None:
					value = "-"
				# Apply translations where needed
				if header in ["payment_type", "payment_status", "car_body_type"]:
					value = _translate_value(header, value)
				cell_type = "Number" if isinstance(value, (int, float)) else "String"
				output.write(f'<Cell><Data ss:Type="{cell_type}">{value}</Data></Cell>\n'.encode("utf-8"))
			output.write(b"</Row>\n")
		output.write(b"</Table>\n</Worksheet>\n")
	output.write(b"</Workbook>\n")
	return output.getvalue()

def _get_merged_appointments_services_rows(appointments):
	"""
	Builds a row set that merges each appointment with its child service records.
	If an appointment has multiple services, multiple rows are produced;
	if none, a row with empty service fields is added.
	"""
	rows = []
	for appt in appointments:
		services = frappe.get_all(
			"Car wash appointment service",
			filters={"parent": appt["name"]},
			fields=["service_name", "duration", "price"]
		)
		if services:
			for svc in services:
				merged = appt.copy()
				merged.update(svc)
				rows.append(merged)
		else:
			row = appt.copy()
			row["service_name"] = "-"
			row["duration"] = "-"
			row["price"] = "-"
			rows.append(row)
	return rows

@frappe.whitelist()
def export_appointments_and_services_to_excel(selected_date=None, start_date=None, end_date=None, car_wash=None):
	"""
	Exports appointments into a multi‑sheet Excel file.

	Sheet "Appointments" contains only the appointment records.
	Sheet "Услуги" contains the merged appointment and service records —
	the data is the same as in the export_appointments_with_services_to_excel method.
	"""
	# Fetch appointments and date information.
	appointments, date_info = _get_appointments(selected_date, start_date, end_date, car_wash)

	# Build data for the "Appointments" sheet (appointment rows and their headers).
	appointment_rows = appointments
	appt_headers = list(appointments[0].keys())
	appt_translations = _get_appointment_column_translations()

	# Build merged appointment and service rows (same as export_appointments_with_services_to_excel).
	merged_rows = _get_merged_appointments_services_rows(appointments)
	# Use the union of appointment keys plus service details.
	service_headers = list(merged_rows[0].keys())
	# Start with the basic appointment translations then add service-specific ones.
	services_translations = _get_appointment_column_translations()
	services_translations.update({
		"service_name": "Услуга",
		"duration": "Длительность",
		"price": "Цена услуги",
	})

	# Prepare sheet data: two sheets – one for appointments and one for services.
	sheets = {
		"Бронирования": (appt_headers, appointment_rows, appt_translations),
		"Услуги": (service_headers, merged_rows, services_translations)
	}

	filecontent = _generate_multi_sheet_excel(sheets)

	frappe.response["type"] = "binary"
	frappe.response["filename"] = f"Car_Wash_Appointments_and_Services_{date_info}.xls"
	frappe.response["filecontent"] = filecontent
	frappe.response["doctype"] = None
