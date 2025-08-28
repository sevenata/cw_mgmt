import frappe

from ..appointments_by_date import get_by_date, get_by_time_period
from ..utils import \
	_generate_datetime_date_list


@frappe.whitelist()
def export_workers_to_xls(from_date, to_date, car_wash):
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
		appointments = get_by_time_period(from_date, to_date, car_wash)
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
