import frappe

ROLES_RESTRICTED = {"Car Wash Administrator", "Car Wash Cashier", "Car Wash Worker"}

def _get_allowed_car_washes_for_user(user: str) -> list:
	if not user:
		user = frappe.session.user
	try:
		print(f"user: {user}")
		car_washes = frappe.get_all(
			"Car wash worker",
			filters={"user": user, "is_deleted": 0, "is_disabled": 0},
			pluck="car_wash",
		)
		return [cw for cw in car_washes if cw]
	except Exception:
		return []

def _is_site_admin(user: str) -> bool:
	return user == "Administrator" or "System Manager" in frappe.get_roles(user)

def _gpc(doctype: str, user=None):
	print(f"user: {user}")
	if not user:
		user = frappe.session.user

	if _is_site_admin(user):
		print('HERE IS ADMIN')
		return None

	if ROLES_RESTRICTED.intersection(set(frappe.get_roles(user))):
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

	if ROLES_RESTRICTED.intersection(set(frappe.get_roles(user))):
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
