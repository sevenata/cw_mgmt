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
def search_car_wash_clients(car_wash: str, query: str | None = None, limit: int = 50, offset: int = 0):
	"""
	Поиск клиентов с возвратом информации о клиенте, его автомобилях и описании клиента
	для конкретной автомойки (если описание есть). Клиенты без описания также включаются.

	Аргументы:
	- car_wash: Идентификатор docname автомойки (`Car wash`).
	- query: Строка поиска (необязательная). Ищет по имени клиента, телефону, номеру авто,
	         имени и фамилии в описании клиента.
	- limit, offset: Пагинация результатов.

	Возвращает структуру вида:
	{
	  "total": <int>,
	  "items": [
	    {
	      "client": {...},
	      "cars": [...],
	      "description": {...} | None
	    }
	  ]
	}
	"""
	if not car_wash:
		raise frappe.ValidationError("car_wash is required")

	params = {"car_wash": car_wash}
	where_clauses = ["1=1"]
	if query:
		params["q"] = f"%{query}%"
		where_clauses.append(
			"("
			"c.customer_name LIKE %(q)s OR "
			"c.phone LIKE %(q)s OR "
			"car.license_plate LIKE %(q)s OR "
			"d.first_name LIKE %(q)s OR "
			"d.last_name LIKE %(q)s"
			")"
		)

	where_sql = " AND ".join(where_clauses)

	# Подсчёт общего количества уникальных клиентов
	count_sql = f"""
		SELECT COUNT(DISTINCT c.name)
		FROM `tabCar wash client` c
		LEFT JOIN `tabCar wash client description` d
		  ON d.client = c.name AND d.car_wash = %(car_wash)s
		LEFT JOIN `tabCar wash car` car
		  ON car.customer = c.name AND IFNULL(car.is_deleted, 0) = 0
		WHERE {where_sql}
	"""
	total = frappe.db.sql(count_sql, params)[0][0]

	# Получаем страницу клиентов
	list_sql = f"""
		SELECT DISTINCT c.name
		FROM `tabCar wash client` c
		LEFT JOIN `tabCar wash client description` d
		  ON d.client = c.name AND d.car_wash = %(car_wash)s
		LEFT JOIN `tabCar wash car` car
		  ON car.customer = c.name AND IFNULL(car.is_deleted, 0) = 0
		WHERE {where_sql}
		ORDER BY c.modified DESC
		LIMIT %(limit)s OFFSET %(offset)s
	"""
	params["limit"] = int(limit)
	params["offset"] = int(offset)
	client_names = [r[0] for r in frappe.db.sql(list_sql, params)]

	if not client_names:
		return {"total": int(total or 0), "items": []}

	client_fields = [
		"name",
		"customer_name",
		"phone",
		"user",
		"image",
	]

	car_fields = [
		"name",
		"license_plate",
		"make",
		"make_name",
		"model",
		"model_name",
		"body_type",
		"year",
		"color",
	]

	description_fields = [
		"name",
		"client",
		"car_wash",
		"company",
		"first_name",
		"last_name",
		"description",
	]

	items = []
	for client_name in client_names:
		client_doc = frappe.db.get_value("Car wash client", client_name, client_fields, as_dict=True)
		cars = frappe.get_all(
			"Car wash car",
			filters={"customer": client_name, "is_deleted": 0},
			fields=car_fields,
			order_by="modified desc",
		)
		desc_list = frappe.get_all(
			"Car wash client description",
			filters={"client": client_name, "car_wash": car_wash},
			fields=description_fields,
			limit=1,
		)
		items.append({
			"client": client_doc,
			"cars": cars,
			"description": (desc_list[0] if desc_list else None),
		})

	return {"total": int(total or 0), "items": items}
