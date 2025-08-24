import frappe
import time

ROLES_RESTRICTED = {"Car Wash Administrator", "Car Wash Cashier", "Car Wash Worker"}

_CACHE_TTL_SECONDS = 300

def _cache_get(key: str):
	data = frappe.cache().get_value(key)
	if not data:
		return None
	try:
		ts = data.get("ts", 0)
		if time.time() - ts < _CACHE_TTL_SECONDS:
			return data.get("value")
	except Exception:
		return None
	return None

def _cache_set(key: str, value):
	frappe.cache().set_value(key, {"ts": time.time(), "value": value})

def _get_roles_for_user(user: str) -> set[str]:
	if not user:
		user = frappe.session.user
	cache_key = f"cwm:roles:{user}"
	cached_roles = _cache_get(cache_key)
	if cached_roles is not None:
		return set(cached_roles)
	roles_list = list(frappe.get_roles(user))
	_cache_set(cache_key, roles_list)
	return set(roles_list)

def _get_allowed_car_washes_for_user(user: str) -> list:
	if not user:
		user = frappe.session.user
	cache_key = f"cwm:allowed_car_washes:{user}"
	cached = _cache_get(cache_key)
	if cached is not None:
		return cached
	try:
		car_washes = frappe.get_all(
			"Car wash worker",
			filters={"user": user, "is_deleted": 0, "is_disabled": 0},
			pluck="car_wash",
		)
		result = [cw for cw in car_washes if cw]
	except Exception:
		result = []
	_cache_set(cache_key, result)
	return result

def _is_site_admin(user: str) -> bool:
	return user == "Administrator" or "System Manager" in _get_roles_for_user(user)

def _gpc(doctype: str, user=None):
	if not user:
		user = frappe.session.user

	if _is_site_admin(user):
		return None

	if ROLES_RESTRICTED.intersection(_get_roles_for_user(user)):
		allowed = _get_allowed_car_washes_for_user(user)
		if not allowed:
			return "1=0"
		in_values = ", ".join([frappe.db.escape(cw) for cw in allowed])
		# doctype → SQL table name: `tab{doctype}`
		return f"`tab{doctype}`.car_wash in ({in_values})"

	return None

def has_permission_restricted(doc, ptype="read", user=None):
	if not user:
		user = frappe.session.user

	if _is_site_admin(user):
		return True

	if ROLES_RESTRICTED.intersection(_get_roles_for_user(user)):
		return bool(getattr(doc, "car_wash", None) in _get_allowed_car_washes_for_user(user))

	return True

# Wrappers per DocType for get_permission_query_conditions
def gpc_car_wash_appointment(user=None): return _gpc("Car wash appointment", user)
def gpc_car_wash_booking(user=None): return _gpc("Car wash booking", user)
def gpc_car_wash_mobile_booking_attempt(user=None): return _gpc("Car wash mobile booking attempt", user)
def gpc_car_wash_feedback(user=None): return _gpc("Car wash feedback", user)
def gpc_worker_ledger_entry(user=None): return _gpc("Worker Ledger Entry", user)
def gpc_car_wash_invoice(user=None): return _gpc("Car wash invoice", user)
def gpc_car_wash_subscription(user=None): return _gpc("Car wash subscription", user)
# добавляй по мере необходимости:
def gpc_car_wash_tariff(user=None): return _gpc("Car wash tariff", user)
def gpc_car_wash_box(user=None): return _gpc("Car wash box", user)
