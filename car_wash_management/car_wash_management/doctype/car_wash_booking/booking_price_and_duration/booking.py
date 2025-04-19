# car_wash/booking.py

import frappe
from typing import List, Dict, Any

from .validation import (
    validate_required_params,
    build_service_counter,
    build_custom_price_map,
)
from .repository import (
    get_valid_service_ids,
    get_car_body_type_fresh,
    get_service_docs,
    get_service_prices,
)
from .calculation import (
    calculate_totals,
    get_services_price_details,
)


@frappe.whitelist(allow_guest=True)
def get_booking_price_and_duration(
    car_wash: str, car: str, services: list
) -> Dict[str, Any]:
    """
    Compute total price & duration for the given car wash booking.
    """
    try:
        validate_required_params(car_wash, car, services)

        service_counter = build_service_counter(services)
        custom_price_map = build_custom_price_map(services)

        valid_ids = get_valid_service_ids(list(service_counter.keys()))
        body_type = get_car_body_type_fresh(car)

        docs = get_service_docs(valid_ids)
        prices = get_service_prices(valid_ids, body_type)

        total_price, total_duration, modifiers, custom_prices, staff_reward_total = calculate_totals(
            service_counter, docs, prices, body_type, custom_price_map
        )

        return {
            "status": "success",
            "total_price": total_price,
            "total_duration": total_duration,
            "staff_reward_total": staff_reward_total,
            "applied_modifiers": modifiers,
            "applied_custom_prices": custom_prices,
        }

    except frappe.ValidationError as ve:
        frappe.log_error(ve.message, "Booking Validation Error")
        return {"status": "error", "message": ve.message}

    except Exception as e:
        frappe.log_error(str(e), "Booking Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def get_booking_services_prices(
    car_wash: str, car: str, services: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Return detailed pricing per service for the given booking.
    """
    try:
        validate_required_params(car_wash, car, services)

        service_counter = build_service_counter(services)
        custom_price_map = build_custom_price_map(services)

        valid_ids = get_valid_service_ids(list(service_counter.keys()))
        body_type = get_car_body_type_fresh(car)

        docs = get_service_docs(valid_ids)
        prices = get_service_prices(valid_ids, body_type)

        service_details = get_services_price_details(
            service_counter, docs, prices, body_type, custom_price_map
        )

        return {"status": "success", "services": service_details}

    except frappe.ValidationError as ve:
        frappe.log_error(ve.message, "Booking Validation Error")
        return {"status": "error", "message": ve.message}

    except Exception as e:
        frappe.log_error(str(e), "Booking Error")
        return {"status": "error", "message": str(e)}
