import frappe

from .booking import get_booking_price_and_duration
from .auto_discounts import (
	apply_recorded_auto_discounts_to_base,
	refresh_recorded_auto_discount_usage,
)


def compute_base_price_and_duration(car_wash, car, services, tariff, **kwargs):
	forward_kwargs = dict(kwargs or {})
	return get_booking_price_and_duration(car_wash, car, services or [], tariff, **forward_kwargs)


def get_disabled_auto_discount_ids_from_request_or_doc(doc):
	"""Extract disabled discount ids from doc or request (form_dict)."""
	disabled_ids = getattr(doc, "disabled_auto_discounts", None)
	if disabled_ids is None:
		maybe = frappe.form_dict.get("disabled_auto_discounts") if hasattr(frappe, "form_dict") else None
		try:
			disabled_ids = frappe.parse_json(maybe) if maybe else []
		except Exception:
			disabled_ids = []
	# try JSON body as well (REST API)
	if not disabled_ids:
		try:
			req = getattr(frappe, "request", None)
			json_body = getattr(req, "json", None) if req else None
			if json_body and isinstance(json_body, dict):
				candidate = json_body.get("disabled_auto_discounts")
				if candidate is not None:
					disabled_ids = candidate
		except Exception:
			pass
	return set(disabled_ids or [])


def set_auto_discount_usage_flags(context_type: str, context_id: str, disabled_ids: set, enable_others: bool = False):
	"""
	Mark usage rows disabled for given ids. Optionally enable others.
	"""
	if not disabled_ids:
		return
	names = frappe.get_all(
		"Car wash auto discount usage",
		filters={
			"context_type": context_type,
			"context_id": context_id,
			"discount_id": ["in", list(disabled_ids)],
		},
		pluck="name",
	)
	for n in names:
		frappe.db.set_value("Car wash auto discount usage", n, "is_disabled", 1)

	if enable_others:
		names_other = frappe.get_all(
			"Car wash auto discount usage",
			filters={
				"context_type": context_type,
				"context_id": context_id,
				"discount_id": ["not in", list(disabled_ids)],
			},
			pluck="name",
		)
		for n in names_other:
			frappe.db.set_value("Car wash auto discount usage", n, "is_disabled", 0)


def refresh_usage(context_type: str, context_id: str, base_services_total: float, base_commission: float):
	"""Refresh recorded usage amounts with current base totals."""
	return refresh_recorded_auto_discount_usage(
		context_type,
		context_id,
		base_services_total=base_services_total,
		base_commission=base_commission,
	)


def apply_usage(context_type: str, context_id: str, base_services_total: float, base_commission: float):
	"""Apply recorded usage to provided base and return applied structure."""
	return apply_recorded_auto_discounts_to_base(
		base_services_total=base_services_total,
		base_commission=base_commission,
		context_type=context_type,
		context_id=context_id,
	)


