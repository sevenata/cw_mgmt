from io import BytesIO

from frappe.model.document import Document
from frappe.utils import flt, cint, today, add_days, getdate, now_datetime, add_to_date

def _generate_datetime_date_list(from_datetime, to_datetime):
	"""
	Generate a list of dates between two datetimes, including partial days.

	Args:
		from_datetime (datetime): Start datetime
		to_datetime (datetime): End datetime

	Returns:
		list: List of date strings in YYYY-MM-DD format
	"""
	from frappe.utils import add_days
	from datetime import datetime, timedelta

	date_list = []
	current_date = from_datetime.date()
	end_date = to_datetime.date()

	while current_date <= end_date:
		date_list.append(str(current_date))
		current_date = add_days(current_date, 1)

	return date_list


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
		"Contract": "Договор",
		"Mixed": "Смешанный"
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
