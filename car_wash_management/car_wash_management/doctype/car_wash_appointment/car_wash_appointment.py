from frappe.model.document import Document
import frappe
from frappe.utils import flt, cint, today, add_days, getdate, now_datetime, add_to_date
from io import StringIO, BytesIO
from ..car_wash_booking.booking_price_and_duration import get_booking_price_and_duration
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
		price_and_duration = get_booking_price_and_duration(self.car_wash, self.car, self.services, self.tariff)
		self.services_total = price_and_duration["total_price"]
		self.duration_total = price_and_duration["total_duration"]
		self.staff_reward_total = price_and_duration["staff_reward_total"]

		if self.starts_on and not self.ends_on and self.duration_total:
			self.ends_on = add_to_date(self.starts_on, seconds=self.duration_total)

		if self.payment_status == "Paid" and self.payment_type and not self.payment_received_on:
			self.payment_received_on = now_datetime()

		# Automatically update booking fields if appointment is updated
		if self.booking:
			booking_doc = frappe.get_doc("Car wash booking", self.booking)
			booking_doc.update({
				'appointment_status': self.workflow_state,
				'appointment_payment_status': self.payment_status,
			})
			booking_doc.save()

	# ---- ДОБАВЬ ЭТИ ДВА ХУКА ----
	def after_insert(self):
		# На создание тоже шлём (например, старт работ)
		self._schedule_push_if_changed(created=True)

	def on_update(self):
		# На любое сохранение шлём только если важные поля реально изменились
		self._schedule_push_if_changed()
		try_sync_worker_earning(self)

	# ---- ВНУТРЕННЕЕ: планирование фоновой отправки после коммита ----
	def _schedule_push_if_changed(self, created: bool = False):
		# какие поля считаем «значимыми» для пуша
		interesting_fields = ("workflow_state")

		changed = self.has_value_changed("workflow_state")

		print('check if changed')
		print(changed)

		# доп. фильтры, если нужно: не слать для удалённых и т.п.
		if not changed or getattr(self, "is_deleted", 0):
			print('skip this')
			return

		print('now here')

		payload = {
			"event": "appointment.status_changed" if not created else "appointment.created",
			"id": self.name,
			"car_wash": self.car_wash,
			"customer": self.customer,
			"status": self.workflow_state,
			"starts_on": self.starts_on,
			"ends_on": self.ends_on,
			"booking": self.booking,
			"box": self.box,
			"payment_status": self.payment_status,
			"ts": str(now_datetime()),
		}

		# вызываем ТОЛЬКО после успешного коммита транзакции
		def _after_commit():
			frappe.db.after_commit(lambda: frappe.enqueue(
                "car_wash_management.api.push_to_nest",
                now=True,                # важно: выполнить синхронно, без RQ
                payload=payload
            ))

		frappe.db.after_commit(_after_commit)



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
		"car_wash_worker",
		"car_wash_worker_name",
		"services_total",
		"staff_reward_total",
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
		fields=["payment_received_on", "services_total", "staff_reward_total"],
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
		"staff_reward_total",
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
			staff_reward = appt.get("staff_reward_total", earnings)

			if worker not in worker_earnings:
				# Ensure we initialize with all dates
				worker_earnings[worker] = {date: 0 for date in date_list}
			worker_earnings[worker][date_str] += staff_reward

			if cashier not in cashier_earnings:
				cashier_earnings[cashier] = {date: 0 for date in date_list}
			cashier_earnings[cashier][date_str] += staff_reward

	# Get percentage values from Car wash settings
	try:
		car_wash_settings = frappe.get_doc("Car wash settings", {"car_wash": car_wash})
		washer_percent = car_wash_settings.get("washer_default_percent_from_service", 30) / 100
		cashier_percent = car_wash_settings.get("cashier_default_percent_from_service", 10) / 100
	except frappe.DoesNotExistError:
		# Use default values if settings don't exist
		washer_percent = 0.3  # 30%
		cashier_percent = 0.1  # 10%

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
		output.write(('<Cell><Data ss:Type="String">{}%</Data></Cell>\n'.format(int(washer_percent * 100))).encode('utf-8'))
		# начисление по проценту из настроек
		earned = row_total * washer_percent
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
		output.write(('<Cell><Data ss:Type="String">{}%</Data></Cell>\n'.format(int(cashier_percent * 100))).encode('utf-8'))
		# начисление по проценту из настроек
		earned = row_total * cashier_percent
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
	# Итог заработка (30% для мойщиков + 10% для кассиров)
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
		"staff_reward_total": "Сумма заработка работника",
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


# ---- Worker earning sync helper ----
def try_sync_worker_earning(doc):
	# Если запись помечена как удалённая — отозвать все связанные начисления и выйти
	if getattr(doc, "is_deleted", 0):
		entries = frappe.get_all(
			"Worker Ledger Entry",
			filters={"entry_type": "Earning", "appointment": doc.name, "docstatus": ["<", 2]},
			fields=["name", "docstatus"],
		)
		for entry in entries:
			name = entry.get("name")
			if not name:
				continue
			if cint(entry.get("docstatus")) == 1:
				frappe.get_doc("Worker Ledger Entry", name).cancel()
			else:
				frappe.get_doc("Worker Ledger Entry", name).delete()
		return

	ready = (
		doc.payment_status == "Paid"
		and bool(doc.work_ended_on)
		and bool(doc.car_wash_worker)
		and not getattr(doc, "is_deleted", 0)
	)

	# Рассчитываем начисления по настройкам автомойки: процент/фикс
	washer_percent = 30
	cashier_percent = 10
	washer_fixed = 0
	cashier_fixed = 0
	try:
		settings = frappe.db.get_value(
			"Car wash settings",
			{"car_wash": doc.car_wash},
			[
				"washer_earning_mode",
				"washer_earning_value",
				"washer_default_percent_from_service",
				"cashier_earning_mode",
				"cashier_earning_value",
				"cashier_default_percent_from_service",
			],
			as_dict=True,
		)
		if settings:
			if settings.get("washer_earning_mode") == "Fixed":
				washer_percent = None
				washer_fixed = cint(settings.get("washer_earning_value") or 0)
			else:
				washer_percent = int(settings.get("washer_default_percent_from_service") or 0)
			if settings.get("cashier_earning_mode") == "Fixed":
				cashier_percent = None
				cashier_fixed = cint(settings.get("cashier_earning_value") or 0)
			else:
				cashier_percent = int(settings.get("cashier_default_percent_from_service") or 0)
	except Exception:
		pass

	# Применяем персональные переопределения для мойщика/кассира
	if washer_percent is not None:
		washer_total = cint(round(flt(doc.services_total or 0) * washer_percent / 100.0))
	else:
		washer_total = cint(washer_fixed)
	try:
		worker_override = frappe.db.get_value(
			"Car wash worker",
			{"name": doc.car_wash_worker},
			["earning_override_mode", "earning_override_value"],
			as_dict=True,
		)
		if worker_override:
			mode = (worker_override.get("earning_override_mode") or "Default").strip()
			val = cint(worker_override.get("earning_override_value") or 0)
			if mode == "Percent":
				washer_total = cint(round(flt(doc.services_total or 0) * (val / 100.0)))
			elif mode == "Fixed":
				washer_total = cint(val)
	except Exception:
		pass

	if cashier_percent is not None:
		cashier_total = cint(round(flt(doc.services_total or 0) * cashier_percent / 100.0))
	else:
		cashier_total = cint(cashier_fixed)
	try:
		cashier_worker = frappe.db.get_value(
			"Car wash worker",
			{"user": doc.owner, "car_wash": doc.car_wash, "is_deleted": 0, "is_disabled": 0},
			["name", "earning_override_mode", "earning_override_value"],
			as_dict=True,
		)
		if cashier_worker and cashier_worker.get("name"):
			mode = (cashier_worker.get("earning_override_mode") or "Default").strip()
			val = cint(cashier_worker.get("earning_override_value") or 0)
			if mode == "Percent":
				cashier_total = cint(round(flt(doc.services_total or 0) * (val / 100.0)))
			elif mode == "Fixed":
				cashier_total = cint(val)
	except Exception:
		pass

	# Начисление для мойщика (основной worker из документа)
	existing_name = frappe.db.get_value(
		"Worker Ledger Entry",
		{
			"entry_type": "Earning",
			"appointment": doc.name,
			"worker": doc.car_wash_worker,
			"docstatus": ["<", 2],
		},
		"name",
	)

	if ready and washer_total > 0:
		if existing_name:
			wle = frappe.get_doc("Worker Ledger Entry", existing_name)
			if cint(wle.amount) != washer_total or wle.docstatus != 1:
				if wle.docstatus == 1:
					# Нельзя редактировать отменённый документ – создаём новый после отмены
					wle.cancel()
					new_wle = frappe.new_doc("Worker Ledger Entry")
					new_wle.worker = doc.car_wash_worker
					new_wle.entry_type = "Earning"
					new_wle.amount = washer_total
					new_wle.company = doc.company
					new_wle.car_wash = doc.car_wash
					new_wle.appointment = doc.name
					new_wle.insert(ignore_permissions=True)
					new_wle.submit()
				else:
					# Черновик можно обновить и провести
					wle.amount = washer_total
					wle.company = doc.company
					wle.car_wash = doc.car_wash
					wle.submit()
		else:
			wle = frappe.new_doc("Worker Ledger Entry")
			wle.worker = doc.car_wash_worker
			wle.entry_type = "Earning"
			wle.amount = washer_total
			wle.company = doc.company
			wle.car_wash = doc.car_wash
			wle.appointment = doc.name
			wle.insert(ignore_permissions=True)
			wle.submit()
	else:
		if existing_name:
			wle = frappe.get_doc("Worker Ledger Entry", existing_name)
			if wle.docstatus == 1:
				wle.cancel()

	# Начисление для кассира (создатель документа, тоже worker)
	cashier_worker = None
	try:
		cashier_worker = frappe.db.get_value(
			"Car wash worker",
			{"user": doc.owner, "car_wash": doc.car_wash, "is_deleted": 0, "is_disabled": 0},
			"name",
		)
	except Exception:
		cashier_worker = None

	if cashier_worker:
		existing_cashier = frappe.db.get_value(
			"Worker Ledger Entry",
			{
				"entry_type": "Earning",
				"appointment": doc.name,
				"worker": cashier_worker,
				"docstatus": ["<", 2],
			},
			"name",
		)

		if ready and cashier_total > 0:
			if existing_cashier:
				cwle = frappe.get_doc("Worker Ledger Entry", existing_cashier)
				if cint(cwle.amount) != cashier_total or cwle.docstatus != 1:
					if cwle.docstatus == 1:
						cwle.cancel()
						new_cwle = frappe.new_doc("Worker Ledger Entry")
						new_cwle.worker = cashier_worker
						new_cwle.entry_type = "Earning"
						new_cwle.amount = cashier_total
						new_cwle.company = doc.company
						new_cwle.car_wash = doc.car_wash
						new_cwle.appointment = doc.name
						new_cwle.insert(ignore_permissions=True)
						new_cwle.submit()
				else:
					cwle.amount = cashier_total
					cwle.company = doc.company
					cwle.car_wash = doc.car_wash
					cwle.submit()
			else:
				cwle = frappe.new_doc("Worker Ledger Entry")
				cwle.worker = cashier_worker
				cwle.entry_type = "Earning"
				cwle.amount = cashier_total
				cwle.company = doc.company
				cwle.car_wash = doc.car_wash
				cwle.appointment = doc.name
				cwle.insert(ignore_permissions=True)
				cwle.submit()
		else:
			if existing_cashier:
				cwle = frappe.get_doc("Worker Ledger Entry", existing_cashier)
				if cwle.docstatus == 1:
					cwle.cancel()
