# car_wash/validation.py

import frappe
from frappe import _
from collections import Counter
from typing import List, Dict, Any


def validate_required_params(
	car_wash: str, car: str, services: List[Dict[str, Any]]
) -> None:
	if not (car_wash and car and services):
		frappe.throw(
			_("Missing required parameters. Provide 'car_wash', 'car' and 'services'.")
		)
	if not isinstance(services, list):
		frappe.throw(_("‘services’ must be a list."))
	if not services:
		frappe.throw(_("At least one service must be provided."))


def build_service_counter(services: List[Dict[str, Any]]) -> Counter[str]:
	"""
    Count how many times each service ID appears.
    """
	counter = Counter()
	for svc in services:
		svc_id = svc.get("service") if isinstance(svc, dict) else getattr(svc, "service", None)
		if not svc_id:
			frappe.throw(_("Each service entry must include a 'service' key."))
		counter[svc_id] += 1
	return counter


def build_custom_price_map(services: List[Dict[str, Any]]) -> Dict[str, float]:
	"""
    Map service_id -> custom_price for any entries that specify one.
    """
	custom_map: Dict[str, float] = {}
	for svc in services:
		if isinstance(svc, dict) and svc.get("custom_price"):
			custom_map[svc["service"]] = svc["custom_price"]
		elif hasattr(svc, "service") and getattr(svc, "custom_price", None):
			custom_map[svc.service] = svc.custom_price
	return custom_map
