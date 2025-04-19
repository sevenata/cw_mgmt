# car_wash/repository.py

import frappe
from frappe import _
from typing import List, Dict, Any


def get_valid_service_ids(service_ids: List[str]) -> List[str]:
    if not service_ids:
        return []

    cache = frappe.cache()
    key = f"valid_services:{','.join(sorted(service_ids))}"
    valid = cache.get_value(key)

    if valid is None:
        valid = frappe.get_all(
            "Car wash service",
            filters={"name": ["in", service_ids], "is_disabled": False, "is_deleted": False},
            pluck="name",
        )
        cache.set_value(key, valid, expires_in_sec=3600)
    missing = set(service_ids) - set(valid)
    if missing:
        frappe.throw(_("Invalid/inactive services: {0}").format(", ".join(missing)))
    return valid


def get_car_body_type_fresh(car_id: str) -> str:
    """
    Always fetch fresh (no cache) to get the latest body_type.
    """
    doc = frappe.get_doc("Car wash car", car_id)
    if not doc.body_type:
        frappe.throw(_("Car must have a 'body_type'."))
    return doc.body_type


def get_service_docs(service_ids: List[str]) -> Dict[str, Any]:
    if not service_ids:
        return {}
    rows = frappe.get_all(
        "Car wash service",
        filters={"name": ["in", service_ids]},
        fields=[
            "name", "title", "price", "duration",
            "price_modifier", "price_modifier_type", "price_modifier_value",
            "apply_price_modifier_to_order_total", "is_price_modifier_active"
        ],
    )
    return {r.name: r for r in rows}


def get_service_prices(service_ids: List[str], body_type: str) -> Dict[str, float]:
    if not service_ids:
        return {}

    cache = frappe.cache()
    key = f"service_prices:{','.join(sorted(service_ids))}:{body_type}"
    prices = cache.get_value(key)

    if prices is None:
        recs = frappe.get_all(
            "Car wash service price",
            filters={
                "base_service": ["in", service_ids],
                "body_type": body_type,
                "is_disabled": False,
                "is_deleted": False,
            },
            fields=["base_service", "price", "staff_reward"],
        )
        # map each service → { price: ..., staff_reward: ... }
        prices = {
            r.base_service: {
                "price":        r.price,
                # if r.staff_reward is None, use 0.0
                "staff_reward": (r.staff_reward or 0.0),
            }
            for r in recs
        }
        cache.set_value(key, prices, expires_in_sec=3600)

    return prices
