from frappe.model.document import Document
import frappe
import uuid
from frappe.utils import flt, cint, today, add_days, getdate, now_datetime, add_to_date
from ...inventory import recalc_products_totals, issue_products_from_rows, cancel_sles_by_appointment, reconcile_issues_for_appointment

from .worker_earnings import try_sync_worker_earning
from .appointments_by_date import get_by_date, get_by_time_period
from ..car_wash_booking.booking_price_and_duration import get_booking_price_and_duration
from ..car_wash_booking.booking_price_and_duration.auto_discounts import record_auto_discount_usage, delete_recorded_auto_discount_usage
from ..car_wash_booking.booking_price_and_duration.workflow_helpers import (
	compute_base_price_and_duration,
	get_disabled_auto_discount_ids_from_request_or_doc,
	set_auto_discount_usage_flags,
	refresh_usage,
	apply_usage,
)
from .excel.export_services_to_excel import export_services_to_excel
from .excel.export_workers_to_excel import export_workers_to_xls

class Carwashappointment(Document):
	"""Workflow:
	- before_insert: initialize counters, default payment, and start timestamps; inherit
	  payment fields from linked booking when paid.
	- validate:
	  - for new docs: compute totals with auto-discounts directly;
	  - for updates: compute base totals via helpers, toggle disabled usage, refresh/apply
	    recorded auto-discounts, then recalc products and timings.
	  - also sync payment timestamp and propagate status to linked booking.
	- after_insert: enqueue push and record snapshot of auto-discount usage.
	- on_update: enqueue push, sync worker earnings, stock issue/revert by payment status,
	  reconcile items if changed while paid, handle soft-delete (revert stock + delete usage).
	- on_trash/on_cancel: revert stock and delete usage.
	Rationale: shared helpers keep pricing/discount application consistent across doctypes.
	"""
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

	# ---- Helpers (internal) ----
	def _get_disabled_ids(self) -> set:
		try:
			return get_disabled_auto_discount_ids_from_request_or_doc(self)
		except Exception:
			return set()

	def _compute_base(self) -> dict:
		return compute_base_price_and_duration(self.car_wash, self.car, self.services, self.tariff, apply_auto_discounts=False)

	def _refresh_and_apply_usage(self, base: dict) -> dict:
		refresh_usage(
			"Appointment",
			self.name,
			base_services_total=base.get("final_services_price", 0.0),
			base_commission=base.get("final_commission", 0.0),
		)
		return apply_usage(
			context_type="Appointment",
			context_id=self.name,
			base_services_total=base.get("final_services_price", 0.0),
			base_commission=base.get("final_commission", 0.0),
		)

	def _set_totals_from_base(self, base: dict) -> None:
		self.duration_total = base["total_duration"]
		self.staff_reward_total = base["staff_reward_total"]

	def _set_totals_from_applied(self, applied: dict) -> None:
		self.services_total = applied["final_services_total"] + applied["final_commission"]

	def _toggle_disabled_usage(self, disabled_ids: set, enable_others: bool = False) -> None:
		if disabled_ids:
			set_auto_discount_usage_flags("Appointment", self.name, disabled_ids, enable_others=enable_others)

	def _record_filtered_usage_for_create(self, base: dict, disabled_ids: set) -> None:
		try:
			full = get_booking_price_and_duration(self.car_wash, self.car, self.services, self.tariff, user=self.customer)
			auto_result = (full.get("auto_discounts", {}) or {}).copy()
			applied = list(auto_result.get("applied_discounts", []) or [])
			filtered_applied = [d for d in applied if d.get("discount_id") not in disabled_ids]
			filtered_auto_result = {
				"applied_discounts": filtered_applied,
				"total_service_discount": 0.0,
				"commission_waived": 0.0,
				"final_services_total": base.get("final_services_price", 0.0),
				"final_commission": base.get("final_commission", 0.0),
				"total_discount": 0.0,
			}
			record_auto_discount_usage(self.car_wash, self.customer, "Appointment", self.name, filtered_auto_result)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Appointment create with disabled discounts failed")

	def _maybe_update_ends_on(self) -> None:
		if self.starts_on and not self.ends_on and self.duration_total:
			self.ends_on = add_to_date(self.starts_on, seconds=self.duration_total)

	def _maybe_update_payment_received(self) -> None:
		if self.payment_status == "Paid" and self.payment_type and not self.payment_received_on:
			self.payment_received_on = now_datetime()

	def _propagate_to_booking(self) -> None:
		if self.booking:
			booking_doc = frappe.get_doc("Car wash booking", self.booking)
			booking_doc.update({
				'appointment_status': self.workflow_state,
				'appointment_payment_status': self.payment_status,
			})
			booking_doc.save()

	def _ensure_usage_recorded_after_insert(self) -> None:
		try:
			if getattr(self, "is_deleted", 0):
				return
			existing = frappe.get_all(
				"Car wash auto discount usage",
				filters={"context_type": "Appointment", "context_id": self.name},
				limit=1,
			)
			if not existing:
				result = get_booking_price_and_duration(self.car_wash, self.car, self.services, self.tariff, user=self.customer)
				auto_result = result.get("auto_discounts", {}) or {}
				record_auto_discount_usage(self.car_wash, self.customer, "Appointment", self.name, auto_result)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Record auto discount usage (appointment after_insert) failed")

	def validate(self):
		# New document: support disabled auto-discounts on create
		if self.is_new():
			disabled_ids = self._get_disabled_ids()
			print('_get_disabled_ids', disabled_ids)
			if disabled_ids:
				base = self._compute_base()
				self._set_totals_from_base(base)
				self._record_filtered_usage_for_create(base, disabled_ids)
				applied = self._refresh_and_apply_usage(base)
				self._set_totals_from_applied(applied)
			else:
				full = get_booking_price_and_duration(self.car_wash, self.car, self.services, self.tariff)
				self.duration_total = full["total_duration"]
				self.staff_reward_total = full["staff_reward_total"]
				self.services_total = full["total_price"]
		else:
			# Update document: use recorded usage and respect disabled flags
			base = self._compute_base()
			self._set_totals_from_base(base)
			try:
				disabled_ids = self._get_disabled_ids()
				self._toggle_disabled_usage(disabled_ids, enable_others=True)
			except Exception:
				frappe.log_error(frappe.get_traceback(), "Mark disabled auto discount usage (appointment) failed")
			applied = self._refresh_and_apply_usage(base)
			self._set_totals_from_applied(applied)

		# Common post-calculation steps
		recalc_products_totals(self)
		self._maybe_update_ends_on()
		self._maybe_update_payment_received()
		self._propagate_to_booking()

	def after_insert(self):
		# На создание тоже шлём (например, старт работ)
		self._schedule_push_if_changed(created=True)
		self._ensure_usage_recorded_after_insert()

	def on_update(self):
		# На любое сохранение шлём только если важные поля реально изменились
		self._schedule_push_if_changed()
		try_sync_worker_earning(self)

		# Автоматическое списание/возврат товаров по изменению статуса оплаты
		try:
			if self.has_value_changed("payment_status"):
				if getattr(self, "payment_status", None) == "Paid":
					issue_products_from_rows(self.car_wash, getattr(self, "products", []) or [], appointment=self.name, release_reserved=True)
				else:
					cancel_sles_by_appointment(self.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Car wash appointment on_update stock flow failed")

		# Дельта-реконсиляция, если уже Paid, а товары изменились
		try:
			if getattr(self, "payment_status", None) == "Paid" and self.has_value_changed("products"):
				reconcile_issues_for_appointment(self)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Car wash appointment reconcile failed")

		# Soft-delete: при установке is_deleted = 1 вернуть стоки (отменить SLE) и удалить usage
		try:
			if self.has_value_changed("is_deleted") and getattr(self, "is_deleted", 0):
				cancel_sles_by_appointment(self.name)
				delete_recorded_auto_discount_usage("Appointment", self.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Car wash appointment soft-delete revert stock failed")

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

		# вызываем ТОЛКО после успешного коммита транзакции
		def _after_commit():
			frappe.db.after_commit(lambda: frappe.enqueue(
				"car_wash_management.api.push_to_nest",
				now=True,                # важно: выполнить синхронно, без RQ
				payload=payload
			))

		frappe.db.after_commit(_after_commit)

	def on_trash(self):
		# перед удалением документа гарантируем возврат товара и удаляем usage
		try:
			cancel_sles_by_appointment(self.name)
			delete_recorded_auto_discount_usage("Appointment", self.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Car wash appointment on_trash revert stock failed")

	def on_cancel(self):
		# при отмене документа вернуть стоки и удалить usage, как и для worker ledger entry
		try:
			cancel_sles_by_appointment(self.name)
			delete_recorded_auto_discount_usage("Appointment", self.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Car wash appointment on_cancel revert stock failed")



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
	return export_workers_to_xls(from_date, to_date, car_wash)

@frappe.whitelist()
def export_appointments_and_services_to_excel(selected_date=None, start_date=None, end_date=None, car_wash=None):
	return export_services_to_excel(selected_date, start_date, end_date, car_wash)
