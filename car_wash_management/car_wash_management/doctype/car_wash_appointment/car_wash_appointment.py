from frappe.model.document import Document
import frappe
from frappe.utils import flt, cint, today, add_days, getdate, now_datetime, add_to_date

from .appointments import _get_appointments, _get_appointment_column_translations, \
	_get_merged_appointments_services_rows
from .utils import _generate_datetime_date_list, _generate_multi_sheet_excel, _translate_value
from .worker_earnings import try_sync_worker_earning
from .appointments_by_date import get_by_date, get_by_time_period
from ..car_wash_booking.booking_price_and_duration import get_booking_price_and_duration

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
	return get_by_date(selected_date, car_wash)

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
	return get_by_time_period(start_date, end_date, car_wash)

@frappe.whitelist()
def export_total_services_to_xls(from_date, to_date, car_wash):
	"""
	Generate an Excel report summarizing worker earnings over a specified date range.
	Now supports both date-only and datetime formats.
	"""
	from io import BytesIO
	from frappe.utils import getdate, add_days, get_datetime

	if not from_date or not to_date:
		frappe.throw("Please provide both from_date and to_date in 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS' format.")

	# Check if dates include time
	from_has_time = ' ' in str(from_date) and ':' in str(from_date)
	to_has_time = ' ' in str(to_date) and ':' in str(to_date)

	# If both dates have time, use precise datetime filtering
	if from_has_time and to_has_time:
		try:
			from_datetime = get_datetime(from_date)
			to_datetime = get_datetime(to_date)
		except ValueError:
			frappe.throw("Invalid datetime format. Please provide valid 'YYYY-MM-DD HH:MM:SS' values.")

		if from_datetime > to_datetime:
			frappe.throw("from_date cannot be later than to_date.")

		# Use precise datetime filtering
		appointments = get_appointments_by_time_period(from_date, to_date, car_wash)
		date_list = _generate_datetime_date_list(from_datetime, to_datetime)
		title_period = f"{from_datetime.strftime('%Y-%m-%d %H:%M')} - {to_datetime.strftime('%Y-%m-%d %H:%M')}"

	else:
		# Fallback to date-only processing (original behavior)
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

		# Step 2: Get appointments for each date
		appointments = []
		for date_str in date_list:
			date_appointments = get_by_date(date_str, car_wash)
			appointments.extend(date_appointments)

		title_period = f"{str(from_date)} - {str(to_date)}"

	# Step 3: Initialize empty earnings dict
	worker_earnings = {}
	cashier_earnings = {}

	# Step 4: Process appointments and calculate earnings
	for appt in appointments:
		worker = appt.get("car_wash_worker_name", "Unknown")
		cashier = appt.get("owner", "Unknown")
		earnings = appt.get("services_total", 0)
		staff_reward = appt.get("staff_reward_total", earnings)

		# Determine the date key for this appointment
		if from_has_time and to_has_time:
			# For datetime mode, use the actual appointment date
			appt_date = appt.get("payment_received_on")
			if appt_date:
				if hasattr(appt_date, 'date'):
					date_key = str(appt_date.date())
				else:
					date_key = str(appt_date)[:10]
			else:
				continue
		else:
			# For date mode, use the date from the loop
			date_key = str(appt.get("payment_received_on", ""))[:10]

		if worker not in worker_earnings:
			# Ensure we initialize with all dates
			worker_earnings[worker] = {date: 0 for date in date_list}
		if date_key in worker_earnings[worker]:
			worker_earnings[worker][date_key] += staff_reward

		if cashier not in cashier_earnings:
			cashier_earnings[cashier] = {date: 0 for date in date_list}
		if date_key in cashier_earnings[cashier]:
			cashier_earnings[cashier][date_key] += staff_reward

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
	title = "Расчёт зарплаты за период " + title_period
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


@frappe.whitelist()
def export_appointments_and_services_to_excel(selected_date=None, start_date=None, end_date=None, car_wash=None):
	"""
	Exports appointments into a multi‑sheet Excel file.
	Now supports both date-only and datetime formats.

	Parameters:
	- selected_date: Single date in "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS" format
	- start_date: Start date in "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS" format
	- end_date: End date in "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS" format
	- car_wash: Car wash name (optional)

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
