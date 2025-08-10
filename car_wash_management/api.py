# car_wash_management/api.py

import frappe
import json
import requests
import datetime
from frappe import _
import frappe
import jwt
import secrets

# from datetime import datetime, timedelta, time
from typing import List, Dict, Optional

from car_wash_management.car_wash_management.doctype.car_wash_appointment.car_wash_appointment_manager import \
	CarWashAppointmentManager
from car_wash_management.car_wash_management.doctype.car_wash_appointment.car_wash_scheduler import \
	CarWashScheduler

import json, hmac, hashlib, requests
import frappe


def push_to_nest(payload: dict):
    try:
        frappe.logger().info(f"[push_to_nest] start payload={payload}")
        body = json.dumps(payload, default=str).encode("utf-8")
        url = frappe.conf.get("nest_webhook_url") or "https://juu-mobile-api.vercel.app/data-streaming/appointments"
        secret = (frappe.conf.get("nest_webhook_secret") or "").encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if secret:
            headers["X-Signature"] = hmac.new(secret, body, hashlib.sha256).hexdigest()

        r = requests.post(url, data=body, headers=headers, timeout=5)
        frappe.logger().info(f"[push_to_nest] done status={r.status_code}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "push_to_nest")


# http://localhost:8001/api/method/car_wash_management.api.get_working_hours?wash_id=8213lrjkg7
@frappe.whitelist()
def get_working_hours(wash_id):
	if not wash_id:
		frappe.throw(_("Doc ID is required"))

	manager = CarWashAppointmentManager(wash_id)
	hours = manager.get_working_hours()

	return hours


# http://localhost:8001/api/method/car_wash_management.api.get_time_intervals?wash_id=8213lrjkg7
@frappe.whitelist()
def get_time_intervals(wash_id, day_of_week):
	if not wash_id:
		frappe.throw(_("Doc ID is required"))

	if not day_of_week:
		frappe.throw(_("Day of week is required"))

	manager = CarWashAppointmentManager(wash_id)
	items = manager.get_time_intervals(day_of_week=day_of_week)

	return items


@frappe.whitelist()
def get_appointments(wash_id):
	if not wash_id:
		frappe.throw(_("Doc ID is required"))

	manager = CarWashAppointmentManager(wash_id)
	items = manager.get_appointments()

	return items


# http://localhost:8001/api/method/car_wash_management.api.get_free_slots?wash_id=8213lrjkg7
@frappe.whitelist()
def get_free_slots(
	car_wash: str,
	date_str: Optional[str] = None,
	step_minutes: int = 15,
	max_results: Optional[int] = None,
	include_capacity: int = 0,
	respect_queue: int = 1,
):
	from datetime import datetime, timedelta, time
	"""
	HTTP-friendly wrapper. Example:
	  frappe.call('path.to.get_free_slots', { car_wash: 'CW-0001', date_str: '2025-08-09', step_minutes: 15 })

	- If date_str is None, uses today.
	"""
	date_ = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.today()
	scheduler = CarWashScheduler(car_wash)
	free = scheduler.get_free_slots_for_date(
		date_=date_,
		step_minutes=int(step_minutes),
		max_results=int(max_results) if max_results else None,
		include_capacity=bool(int(include_capacity)),
		respect_queue=bool(int(respect_queue)),
		debug=True
	)
	return free


@frappe.whitelist()
def get_car_wash_services_with_prices():
	# Fetch all Car wash service records
	services = frappe.get_all(
		"Car wash service",
		fields=["*"],  # Fetch all fields
		filters={"is_deleted": 0}  # Optional: Exclude deleted services
	)

	for service in services:
		# Fetch related prices from Car wash service price
		prices = frappe.get_all(
			"Car wash service price",
			fields=["price", "body_type"],
			filters={"base_service": service["name"]}
		)
		# Add prices field to each service
		service["prices"] = prices

	return services


# OpenWeatherMap API Config
OPENWEATHERMAP_API_URL = "https://api.openweathermap.org/data/2.5/forecast"
CITY_ID = 1526273  # Astana's city ID
API_KEY = "61c936a3c66bc75fe6d12c42d1998738"  # Replace with your actual API key


# http://localhost:8000/api/method/car_wash_management.api.get_weather
@frappe.whitelist()
def get_weather():
	import json

	"""
	Fetch weather forecast for Astana and cache it for 6 hours.
	"""
	# Cache key for storing weather data
	cache_key = "weather_forecast_astana"

	# Check if cached data exists
	cached_data = frappe.cache().get_value(cache_key)
	if cached_data:
		return frappe.parse_json(cached_data)

	# Fetch weather forecast data from OpenWeatherMap
	try:
		url = f"{OPENWEATHERMAP_API_URL}?id={CITY_ID}&appid={API_KEY}&units=metric"
		response = requests.get(url)
		response.raise_for_status()  # Raise error for non-200 responses
		weather_data = response.json()

		# Save serialized data to cache for 6 hours
		frappe.cache().set_value(cache_key, weather_data, expires_in_sec=6 * 60 * 60)

		return weather_data
	except requests.exceptions.RequestException as e:
		frappe.throw(f"Error fetching weather data: {str(e)}")
	except ValueError as e:
		frappe.throw(f"Serialization error: {str(e)}")


@frappe.whitelist(allow_guest=True)
def login_and_get_jwt(email, password):
	from frappe.utils.password import check_password
	"""
	Принимает логин (email) и пароль пользователя,
	возвращает JWT-токен с api_key и api_secret в payload.
	При этом api_key/secret храним в отдельном DocType: "User API Keys".
	"""
	# 1. Проверяем, есть ли пользователь
	user_name = frappe.db.get_value("User", {"email": email, "enabled": 1}, "name")
	if not user_name:
		frappe.throw("Пользователь не найден или отключен", exc=frappe.AuthenticationError)

	# 2. Проверяем пароль (стандартная логика)
	try:
		check_password(user_name, password)
	except frappe.AuthenticationError:
		frappe.throw("Неверные учетные данные", exc=frappe.AuthenticationError)

	# 3. Ищем в нашем DocType "User API Keys" активную запись
	#    Предположим, что на одного пользователя - одна запись is_active=1
	user_api_key_name = frappe.db.get_value(
		"User API Keys",
		{"user": user_name, "is_active": 1},
		"name"
	)

	user_car_wash = frappe.db.get_value(
		"Car wash worker",
		{"user": user_name},
		"car_wash"
	)

	if not user_car_wash:
		frappe.throw("Пользователь не подключен к системе", exc=frappe.AuthenticationError)

	if user_api_key_name:
		# У пользователя уже есть ключ
		user_api_keys_doc = frappe.get_doc("User API Keys", user_api_key_name)
	else:

		user_details = frappe.get_doc("User", email)
		api_secret = frappe.generate_hash(length=15)
		# if api key is not set generate api key
		if not user_details.api_key:
			api_key = frappe.generate_hash(length=15)
			user_details.api_key = api_key
		user_details.api_secret = api_secret
		user_details.save(ignore_permissions=True)

		# Создаем новую запись
		user_api_keys_doc = frappe.get_doc({
			"doctype": "User API Keys",
			"user": user_name,
			"api_key": user_details.api_key,
			"api_secret": api_secret,
			"is_active": 1
		})
		user_api_keys_doc.insert(ignore_permissions=True)

	# 4. Берём JWT-настройки
	jwt_settings = frappe.get_single("JWT Settings")
	if not jwt_settings or not jwt_settings.jwt_secret_key:
		frappe.throw("JWT Settings не настроены или секретный ключ отсутствует")

	secret_key = jwt_settings.jwt_secret_key
	algorithm = jwt_settings.algorithm
	expiration_time = jwt_settings.expiration_time or 30  # минут

	# 5. Формируем payload
	payload = {
		"sub": user_name,
		"api_key": user_api_keys_doc.api_key,
		"api_secret": user_api_keys_doc.api_secret,  # хранится в DocType
		"car_wash": user_car_wash,
		"iat": datetime.datetime.utcnow(),
		"exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=int(expiration_time))
	}

	# 6. Генерируем JWT
	token = jwt.encode(payload, secret_key, algorithm=algorithm)
	if isinstance(token, bytes):
		token = token.decode("utf-8")

	return {
		"token": token
	}
