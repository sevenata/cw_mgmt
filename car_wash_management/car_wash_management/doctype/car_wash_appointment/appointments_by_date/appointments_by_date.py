from frappe.model.document import Document
import frappe
from frappe.utils import flt, cint, today, add_days, getdate, now_datetime, add_to_date

def get_by_date(selected_date=None, car_wash=None):
	"""
	Extracts Car Wash Appointment records for the selected date.
	Now supports both date-only and datetime formats.

	Args:
	selected_date (str): The date in "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS" format to filter appointments.

	Returns:
	list: A list of appointments with the specified fields.
	"""
	if not selected_date:
		frappe.throw("Please provide a selected_date in 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS' format.")

	# Check if selected_date includes time
	selected_has_time = ' ' in str(selected_date) and ':' in str(selected_date)

	if selected_has_time:
		# Selected date has time - use precise datetime filtering
		try:
			from frappe.utils import get_datetime
			selected_datetime = get_datetime(selected_date)
		except ValueError:
			frappe.throw("Invalid datetime format. Please provide a valid 'YYYY-MM-DD HH:MM:SS' format.")

		# For datetime, we need to handle the specific time
		# Extract the date part and create a time range for that specific day
		date_part = str(selected_datetime.date())
		time_part = selected_datetime.time()

		# Create filters for the specific time on that date
		filters = {
			"payment_received_on": ["between",
									[f"{date_part} {time_part}", f"{date_part} 23:59:59"]],
			"is_deleted": 0,
			"payment_status": "Paid",
			"car_wash": car_wash
		}
	else:
		# Fallback to date-only processing (original behavior)
		try:
			getdate(selected_date)
		except ValueError:
			frappe.throw("Invalid date format. Please provide a valid 'YYYY-MM-DD' format.")

		# Define the filters for full day
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
		"custom_payment_method",
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


def get_by_time_period(start_date=None, end_date=None, car_wash=None):
	"""
	Extracts Car Wash Appointment records between the given start and end dates.
	Now supports both date-only and datetime formats.

	Args:
		start_date (str): The start date in "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS" format.
		end_date (str): The end date in "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS" format.
		car_wash (str, optional): Filter appointments by a specific car wash.

	Returns:
		list: A list of appointments with the specified fields.
	"""
	from frappe.utils import getdate, get_datetime

	if not start_date or not end_date:
		frappe.throw("Please provide both start_date and end_date in 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS' format.")

	# Check if dates include time
	start_has_time = ' ' in str(start_date) and ':' in str(start_date)
	end_has_time = ' ' in str(end_date) and ':' in str(end_date)

	# If both dates have time, use precise datetime filtering
	if start_has_time and end_has_time:
		try:
			start_datetime = get_datetime(start_date)
			end_datetime = get_datetime(end_date)
		except ValueError:
			frappe.throw("Invalid datetime format. Please provide valid 'YYYY-MM-DD HH:MM:SS' values.")

		if start_datetime > end_datetime:
			frappe.throw("start_date cannot be later than end_date.")

		# Use precise datetime filtering
		start_datetime_str = str(start_datetime)
		end_datetime_str = str(end_datetime)
	else:
		# Fallback to date-only processing (original behavior)
		try:
			getdate(start_date)
			getdate(end_date)
		except ValueError:
			frappe.throw("Invalid date format. Please provide valid 'YYYY-MM-DD' dates for both start_date and end_date.")

		# Define the filters. Include car_wash filter only if provided.
		start_datetime_str = f"{start_date} 00:00:00"
		end_datetime_str = f"{end_date} 23:59:59"

	# Define the filters. Include car_wash filter only if provided.
	filters = {
		"payment_received_on": ["between", [start_datetime_str, end_datetime_str]],
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
		"custom_payment_method",
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
