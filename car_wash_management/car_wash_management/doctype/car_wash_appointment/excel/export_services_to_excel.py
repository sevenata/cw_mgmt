import frappe

from ..appointments import _get_appointments, \
    _get_appointment_column_translations, _get_merged_appointments_services_rows
from ..utils import _translate_value, _generate_multi_sheet_excel


@frappe.whitelist()
def export_services_to_excel(selected_date=None, start_date=None, end_date=None, car_wash=None):
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

	# Replace "Custom" payment types with corresponding custom method titles for display
	custom_method_names = {
		appt.get("custom_payment_method")
		for appt in appointments
		if appt.get("payment_type") and appt.get("payment_type").lower() == "custom" and appt.get("custom_payment_method")
	}

	# Additionally collect custom method names from mixed payments
	mixed_parents = [a["name"] for a in appointments if a.get("payment_type") == "Mixed"]
	mixed_rows = []
	if mixed_parents:
		mixed_rows = frappe.get_all(
			"Car wash mixed payment",
			filters={"parent": ["in", mixed_parents]},
			fields=["parent", "payment_type", "amount", "custom_payment_method"],
		)
		for row in mixed_rows:
			if row.get("payment_type") and row["payment_type"].lower() == "custom" and row.get("custom_payment_method"):
				custom_method_names.add(row["custom_payment_method"])

	name_to_title = {}
	if custom_method_names:
		methods = frappe.get_all(
			"Car wash custom payment method",
			filters={"name": ["in", list(custom_method_names)]},
			fields=["name", "title"],
		)
		name_to_title = {m["name"]: (m.get("title") or m["name"]) for m in methods}

	# Apply single Custom mapping
	for appt in appointments:
		if appt.get("payment_type") and appt.get("payment_type").lower() == "custom":
			method_name = appt.get("custom_payment_method")
			if method_name:
				appt["payment_type"] = name_to_title.get(method_name, appt["payment_type"])

	# Build human-readable Mixed composition
	if mixed_rows:
		from collections import defaultdict
		parent_to_parts = defaultdict(list)
		for row in mixed_rows:
			ptype = row.get("payment_type") or ""
			amount = row.get("amount")
			if ptype.lower() == "custom":
				cm_name = row.get("custom_payment_method")
				display_name = name_to_title.get(cm_name, cm_name or "Custom")
			else:
				# translate standard payment names
				display_name = _translate_value("payment_type", ptype)
			part = f"{display_name} {amount}"
			parent_to_parts[row["parent"]].append(part)

		for appt in appointments:
			if appt.get("name") in parent_to_parts:
				parts = "; ".join(parent_to_parts[appt["name"]])
				appt["payment_type"] = f"Смешанный: {parts}"

	# Build data for the "Appointments" sheet (appointment rows and their headers).
	# Remove auxiliary field from export columns
	for appt in appointments:
		if "custom_payment_method" in appt:
			appt.pop("custom_payment_method", None)

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
