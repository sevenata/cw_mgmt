from frappe.model.document import Document
import frappe
from frappe.utils import flt, cint, today, add_days, getdate, now_datetime, add_to_date

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

	# Fetch cashier worker once (Fix for Issue #5)
	cashier_worker_name = None
	try:
		cashier_worker = frappe.db.get_value(
			"Car wash worker",
			{"user": doc.owner, "car_wash": doc.car_wash, "is_deleted": 0, "is_disabled": 0},
			["name", "earning_override_mode", "earning_override_value"],
			as_dict=True,
		)
		if cashier_worker and cashier_worker.get("name"):
			cashier_worker_name = cashier_worker.get("name")
	except Exception:
		pass

	# Calculate cashier total
	if cashier_percent is not None:
		cashier_total = cint(round(flt(doc.services_total or 0) * cashier_percent / 100.0))
	else:
		cashier_total = cint(cashier_fixed)
	
	# Apply cashier's personal override if exists
	if cashier_worker and cashier_worker.get("name"):
		mode = (cashier_worker.get("earning_override_mode") or "Default").strip()
		val = cint(cashier_worker.get("earning_override_value") or 0)
		if mode == "Percent":
			cashier_total = cint(round(flt(doc.services_total or 0) * (val / 100.0)))
		elif mode == "Fixed":
			cashier_total = cint(val)

	# Fix for Issue #8: Clean up orphaned earnings when worker changes
	# First, get ALL existing earnings for this appointment (regardless of worker)
	all_existing_earnings = frappe.get_all(
		"Worker Ledger Entry",
		filters={
			"entry_type": "Earning",
			"appointment": doc.name,
			"docstatus": ["<", 2],
		},
		fields=["name", "worker", "docstatus"],
	)
	
	# Determine which workers SHOULD have earnings based on current state
	expected_workers = {}
	if ready and washer_total > 0 and doc.car_wash_worker:
		expected_workers[doc.car_wash_worker] = {"amount": washer_total, "role": "washer"}
	if ready and cashier_total > 0 and cashier_worker_name:
		expected_workers[cashier_worker_name] = {"amount": cashier_total, "role": "cashier"}
	
	# Cancel/delete earnings for workers who shouldn't have them (orphaned earnings)
	for entry in all_existing_earnings:
		worker = entry.get("worker")
		if worker not in expected_workers:
			# This worker should NOT have an earning - remove it
			try:
				wle = frappe.get_doc("Worker Ledger Entry", entry.get("name"))
				if entry.get("docstatus") == 1:
					wle.cancel()
				else:
					wle.delete()
			except Exception:
				frappe.log_error(
					frappe.get_traceback(),
					f"Failed to clean up orphaned earning for worker {worker}"
				)

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

	# Fix for Issues #1, #3, #4: Check both ready AND washer_total > 0
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
					# Fix for Issue #4: Set posting_datetime from appointment
					new_wle.posting_datetime = doc.payment_received_on or doc.work_ended_on
					new_wle.insert(ignore_permissions=True)
					new_wle.submit()
				else:
					# Черновик можно обновить и провести
					wle.amount = washer_total
					wle.company = doc.company
					wle.car_wash = doc.car_wash
					# Fix for Issue #4: Set posting_datetime from appointment
					wle.posting_datetime = doc.payment_received_on or doc.work_ended_on
					wle.submit()
		else:
			wle = frappe.new_doc("Worker Ledger Entry")
			wle.worker = doc.car_wash_worker
			wle.entry_type = "Earning"
			wle.amount = washer_total
			wle.company = doc.company
			wle.car_wash = doc.car_wash
			wle.appointment = doc.name
			# Fix for Issue #4: Set posting_datetime from appointment
			wle.posting_datetime = doc.payment_received_on or doc.work_ended_on
			wle.insert(ignore_permissions=True)
			wle.submit()
	else:
		# Fix for Issue #1 & #3: Cancel/delete regardless of ready status
		# This ensures earnings are removed when amount becomes 0 or appointment is not ready
		if existing_name:
			wle = frappe.get_doc("Worker Ledger Entry", existing_name)
			if wle.docstatus == 1:
				wle.cancel()
			elif wle.docstatus == 0:  # Fix for Issue #3: Delete draft entries
				wle.delete()

	# Начисление для кассира (создатель документа, тоже worker)
	# Fix for Issue #5: Use cashier_worker_name from earlier lookup
	if cashier_worker_name:
		existing_cashier = frappe.db.get_value(
			"Worker Ledger Entry",
			{
				"entry_type": "Earning",
				"appointment": doc.name,
				"worker": cashier_worker_name,
				"docstatus": ["<", 2],
			},
			"name",
		)

		# Fix for Issues #1, #3, #4: Check both ready AND cashier_total > 0
		if ready and cashier_total > 0:
			if existing_cashier:
				cwle = frappe.get_doc("Worker Ledger Entry", existing_cashier)
				if cint(cwle.amount) != cashier_total or cwle.docstatus != 1:
					if cwle.docstatus == 1:
						cwle.cancel()
						new_cwle = frappe.new_doc("Worker Ledger Entry")
						new_cwle.worker = cashier_worker_name
						new_cwle.entry_type = "Earning"
						new_cwle.amount = cashier_total
						new_cwle.company = doc.company
						new_cwle.car_wash = doc.car_wash
						new_cwle.appointment = doc.name
						# Fix for Issue #4: Set posting_datetime from appointment
						new_cwle.posting_datetime = doc.payment_received_on or doc.work_ended_on
						new_cwle.insert(ignore_permissions=True)
						new_cwle.submit()
					else:
						cwle.amount = cashier_total
						cwle.company = doc.company
						cwle.car_wash = doc.car_wash
						# Fix for Issue #4: Set posting_datetime from appointment
						cwle.posting_datetime = doc.payment_received_on or doc.work_ended_on
						cwle.submit()
			else:
				cwle = frappe.new_doc("Worker Ledger Entry")
				cwle.worker = cashier_worker_name
				cwle.entry_type = "Earning"
				cwle.amount = cashier_total
				cwle.company = doc.company
				cwle.car_wash = doc.car_wash
				cwle.appointment = doc.name
				# Fix for Issue #4: Set posting_datetime from appointment
				cwle.posting_datetime = doc.payment_received_on or doc.work_ended_on
				cwle.insert(ignore_permissions=True)
				cwle.submit()
		else:
			# Fix for Issue #1 & #3: Cancel/delete regardless of ready status
			# This ensures earnings are removed when amount becomes 0 or appointment is not ready
			if existing_cashier:
				cwle = frappe.get_doc("Worker Ledger Entry", existing_cashier)
				if cwle.docstatus == 1:
					cwle.cancel()
				elif cwle.docstatus == 0:  # Fix for Issue #3: Delete draft entries
					cwle.delete()
