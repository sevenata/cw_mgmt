from frappe.model.document import Document
import frappe
from frappe.utils import flt, cint, today, add_days, getdate, now_datetime, add_to_date

from .worker_earnings import try_sync_worker_earning
from .appointments_by_date import get_by_date, get_by_time_period
from ..car_wash_booking.booking_price_and_duration import get_booking_price_and_duration
from .excel.export_services_to_excel import export_services_to_excel
from .excel.export_workers_to_excel import export_workers_to_xls

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
	return export_workers_to_xls(from_date, to_date, car_wash)

@frappe.whitelist()
def export_appointments_and_services_to_excel(selected_date=None, start_date=None, end_date=None, car_wash=None):
	return export_services_to_excel(selected_date, start_date, end_date, car_wash)
