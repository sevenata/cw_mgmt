# Copyright (c) 2024, Rifat Dzhumagulov and contributors
# For license information, please see license.txt

import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import Count, Sum, Max, Min
from pypika.terms import Case
from frappe.model.document import Document
from frappe.utils import now_datetime



class Carwashclient(Document):
	def get_statistics(self, car_wash: str | None = None, limit: int = 5, cache_ttl_sec: int = 1800, force_refresh: int = 0):
		"""
		Возвращает агрегированную статистику по клиенту за периоды:
		- текущий месяц (month)
		- текущий год (year)
		- всё время (all_time)

		На каждый период считаются: total_appointments, paid_appointments, spent_total, avg_ticket,
		last_visit_on, first_visit_on, last_payment_on, unique_cars, top_services, by_status.
		"""
		# Ключ кэша (без дат, только фиксированные периоды)
		cache_key = f"client_stats:v2:{self.name}:{car_wash or ''}:limit={int(limit)}:ttl={int(cache_ttl_sec)}"
		if not bool(int(force_refresh)):
			cached = frappe.cache().get_value(cache_key)
			if cached:
				return frappe.parse_json(cached)

		Appointment = DocType("Car wash appointment")
		ApptService = DocType("Car wash appointment service")
		Service = DocType("Car wash service")

		base_conditions = (Appointment.customer == self.name) & (Appointment.is_deleted == 0)
		if car_wash:
			base_conditions = base_conditions & (Appointment.car_wash == car_wash)

		now_dt = now_datetime()
		month_start = now_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
		year_start = now_dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

		def compute_period_stats(period_start=None, period_end=None):
			conditions = base_conditions
			if period_start and period_end:
				conditions = conditions & Appointment.starts_on.between(period_start, period_end)

			# totals
			total_row = (
				frappe.qb.from_(Appointment)
				.select(Count("*").as_("cnt"))
				.where(conditions)
			).run(as_dict=True)
			total_cnt = (total_row or [{"cnt": 0}])[0]["cnt"]

			# paid totals (strictly by services_total)
			params = {"customer": self.name}
			car_wash_clause = " AND car_wash = %(car_wash)s" if car_wash else ""
			if car_wash:
				params["car_wash"] = car_wash
			date_clause = ""
			if period_start and period_end:
				date_clause = " AND starts_on BETWEEN %(start_date)s AND %(end_date)s"
				params["start_date"] = period_start
				params["end_date"] = period_end
			row = frappe.db.sql(
				f"""
					SELECT COUNT(*) AS cnt,
					       IFNULL(SUM(services_total), 0) AS spent
					FROM `tabCar wash appointment`
					WHERE customer = %(customer)s
					  AND is_deleted = 0
					  AND payment_status = 'Paid'{car_wash_clause}{date_clause}
				""",
				params,
				as_dict=1,
			)
			paid_cnt = int((row or [{"cnt": 0}])[0]["cnt"]) or 0
			spent_total = float((row or [{"spent": 0}])[0]["spent"]) or 0.0

			# last/first visit and last payment
			lf_row = (
				frappe.qb.from_(Appointment)
				.select(
					Max(Appointment.starts_on).as_("last_visit_on"),
					Min(Appointment.starts_on).as_("first_visit_on"),
					Max(Appointment.payment_received_on).as_("last_payment_on"),
				)
				.where(conditions)
			).run(as_dict=True)
			lf = (lf_row or [{}])[0]

			# unique cars
			unique_cars = 0
			if total_cnt:
				params = {"customer": self.name}
				car_wash_clause = " AND car_wash = %(car_wash)s" if car_wash else ""
				if car_wash:
					params["car_wash"] = car_wash
				date_clause = ""
				if period_start and period_end:
					date_clause = " AND starts_on BETWEEN %(start_date)s AND %(end_date)s"
					params["start_date"] = period_start
					params["end_date"] = period_end
				unique_cars = frappe.db.sql(
					f"""
						SELECT COUNT(DISTINCT car)
						FROM `tabCar wash appointment`
						WHERE customer = %(customer)s AND is_deleted = 0{car_wash_clause}{date_clause}
					""",
					params,
				)[0][0]

			# top services
			top_services = (
				frappe.qb.from_(ApptService)
				.join(Appointment).on(ApptService.parent == Appointment.name)
				.join(Service).on(ApptService.service == Service.name)
				.select(Service.name.as_("service"), Service.title.as_("service_title"), Count("*").as_("count"))
				.where(conditions)
				.groupby(Service.title, Service.name)
				.orderby(Count("*"), order=frappe.qb.desc)
				.limit(int(limit))
			).run(as_dict=True) or []

			# by status
			by_status_rows = (
				frappe.qb.from_(Appointment)
				.select(Appointment.workflow_state, Count("*").as_("count"))
				.where(conditions)
				.groupby(Appointment.workflow_state)
			).run(as_dict=True) or []
			by_status = {r.get("workflow_state") or "": r.get("count") or 0 for r in by_status_rows}

			avg_ticket = (float(spent_total) / float(paid_cnt)) if paid_cnt else 0.0
			return {
				"total_appointments": total_cnt,
				"paid_appointments": paid_cnt,
				"spent_total": float(spent_total or 0),
				"avg_ticket": float(avg_ticket or 0),
				"last_visit_on": lf.get("last_visit_on"),
				"first_visit_on": lf.get("first_visit_on"),
				"last_payment_on": lf.get("last_payment_on"),
				"unique_cars": int(unique_cars or 0),
				"top_services": top_services,
				"by_status": by_status,
			}

		result = {
			"customer": self.name,
			"periods": {
				"month": compute_period_stats(month_start, now_dt),
				"year": compute_period_stats(year_start, now_dt),
				"all_time": compute_period_stats(None, None),
			},
		}

		# Сохраняем в кэш
		frappe.cache().set_value(cache_key, result, expires_in_sec=int(cache_ttl_sec))
		return result



@frappe.whitelist()
def get_client_statistics(client_id: str, car_wash: str | None = None, limit: int = 5, cache_ttl_sec: int = 1800, force_refresh: int = 0):
	"""
	Публичный API для получения статистики по клиенту.
	"""
	doc = frappe.get_doc("Car wash client", client_id)
	return doc.get_statistics(
		car_wash=car_wash,
		limit=int(limit),
		cache_ttl_sec=int(cache_ttl_sec),
		force_refresh=int(force_refresh),
	)


@frappe.whitelist()
def search_car_wash_clients(
    car_wash: str,
    query: str | None = None,
    limit: int = 50,
    include_total: int = 1,
    cursor_modified: str | None = None,
    cursor_name: str | None = None,
):
	from .search_service import search_clients

	return search_clients(
		car_wash=car_wash,
		query=query,
		limit=int(limit),
		include_total=int(include_total),
		cursor_modified=cursor_modified,
		cursor_name=cursor_name,
	)


@frappe.whitelist()
def set_client_tags(client_id: str, car_wash: str, tag_ids: list | None = None):
	"""
	Идёмпотентно задаёт точный набор тегов клиенту в рамках конкретной мойки.
	Принимает только tag_ids (name из `Car wash tag`). Если описания клиента для мойки нет — создаём.
	"""
	if isinstance(tag_ids, str):
		try:
			tag_ids = frappe.parse_json(tag_ids)
		except Exception:
			tag_ids = []

	if not tag_ids:
		tag_ids = []

	# Validate tag_ids belong to the car_wash
	valid = set(
		name for name, in frappe.db.sql(
			"""
			SELECT name FROM `tabCar wash tag`
			WHERE car_wash=%(car_wash)s AND is_active=1 AND name IN %(ids)s
			""",
			{"car_wash": car_wash, "ids": tuple(tag_ids or ["__none__"])},
		)
	)
	if set(tag_ids or []) - valid:
		raise frappe.ValidationError("Some tags do not belong to this car wash or are inactive")

	# Get or create description
	desc_list = frappe.get_all(
		"Car wash client description",
		filters={"client": client_id, "car_wash": car_wash},
		fields=["name"],
		limit=1,
	)
	if desc_list:
		doc = frappe.get_doc("Car wash client description", desc_list[0]["name"])
	else:
		doc = frappe.new_doc("Car wash client description")
		doc.client = client_id
		doc.car_wash = car_wash

	# Replace tags child table
	doc.set("tags", [])
	for tag_id in (tag_ids or []):
		doc.append("tags", {"tag": tag_id})
	
	doc.save()
	return {"ok": True, "client": client_id, "car_wash": car_wash, "tag_ids": tag_ids}


@frappe.whitelist()
def get_client_description(client_id: str, car_wash: str):
	"""
	Возвращает описание клиента (в контексте мойки) вместе с тегами.
	Не создаёт запись, если её нет — вернёт пустой объект.
	"""
	if not client_id or not car_wash:
		raise frappe.ValidationError("client_id and car_wash are required")

	row = frappe.get_all(
		"Car wash client description",
		filters={"client": client_id, "car_wash": car_wash},
		fields=[
			"name",
			"client",
			"car_wash",
			"description",
			"first_name",
			"last_name",
			"birth_date",
			"email",
			"telegram",
			"whatsapp",
			"allergies_notes",
			"staff_preferences",
		],
		limit=1,
	)
	if not row:
		return {}
	desc = row[0]

	# Fetch tags with titles and colors
	tags = frappe.db.sql(
		"""
		SELECT dt.tag AS tag, t.title AS tag_title, IFNULL(t.color, '') AS color
		FROM `tabCar wash client description tag` dt
		JOIN `tabCar wash tag` t ON t.name = dt.tag
		WHERE dt.parent = %s
		ORDER BY t.title ASC
		""",
		(desc["name"],),
		as_dict=1,
	)
	desc["tags"] = tags or []
	return desc
