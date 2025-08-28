from frappe.model.document import Document
import frappe
from frappe.utils import flt, cint, today, add_days, getdate, now_datetime, add_to_date
from .appointments_by_date import get_by_date, get_by_time_period

def _get_appointments(selected_date, start_date, end_date, car_wash):
	"""
	Fetch appointments based on a selected date or a date range.
	Now supports both date-only and datetime formats.
	Returns a tuple (appointments, date_info) where date_info is used for naming the file.
	"""
	if start_date and end_date:
		# Check if dates include time
		start_has_time = ' ' in str(start_date) and ':' in str(start_date)
		end_has_time = ' ' in str(end_date) and ':' in str(end_date)

		if start_has_time and end_has_time:
			# Both dates have time - use precise datetime filtering
			try:
				from frappe.utils import get_datetime
				start_datetime = get_datetime(start_date)
				end_datetime = get_datetime(end_date)
			except ValueError:
				frappe.throw("Invalid datetime format for start_date or end_date. Please provide valid 'YYYY-MM-DD HH:MM:SS' dates.")
			appointments = get_by_time_period(start_date, end_date, car_wash)
			date_info = f"{start_datetime.strftime('%Y-%m-%d_%H-%M')}_to_{end_datetime.strftime('%Y-%m-%d_%H-%M')}"
		else:
			# Fallback to date-only processing (original behavior)
			try:
				getdate(start_date)
				getdate(end_date)
			except ValueError:
				frappe.throw("Invalid date format for start_date or end_date. Please provide valid 'YYYY-MM-DD' dates.")
			appointments = get_by_time_period(start_date, end_date, car_wash)
			date_info = f"{start_date}_to_{end_date}"
	elif selected_date:
		# Check if selected_date includes time
		selected_has_time = ' ' in str(selected_date) and ':' in str(selected_date)

		if selected_has_time:
			# Selected date has time - use precise datetime filtering
			try:
				from frappe.utils import get_datetime
				selected_datetime = get_datetime(selected_date)
			except ValueError:
				frappe.throw("Invalid datetime format for selected_date. Please provide a valid 'YYYY-MM-DD HH:MM:SS' format.")
			appointments = get_by_date(selected_date, car_wash)
			date_info = f"{selected_datetime.strftime('%Y-%m-%d_%H-%M')}"
		else:
			# Fallback to date-only processing (original behavior)
			try:
				getdate(selected_date)
			except ValueError:
				frappe.throw("Invalid date format for selected_date. Please provide a valid 'YYYY-MM-DD' format.")
			appointments = get_by_date(selected_date, car_wash)
			date_info = selected_date
	else:
		frappe.throw("Please provide either selected_date or both start_date and end_date in 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS' format.")

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
