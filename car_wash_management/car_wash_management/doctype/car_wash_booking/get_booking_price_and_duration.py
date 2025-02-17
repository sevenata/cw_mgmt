import frappe
from frappe import _
from collections import Counter
from typing import List, Dict, Any, Optional


@frappe.whitelist(allow_guest=True)
def get_booking_price_and_duration(car_wash: str, car: str, services: list) -> Dict[str, Any]:
    """
    Calculates the total price and total duration for a Car Wash Booking based on selected services and car body type.

    :param car_wash: Name (ID) of the Car Wash (Link to Car wash DocType).
    :param car: Name (ID) of the Car (Link to Car wash car DocType).
    :param services: List of services with details. Example:
                     [
                       {"service": "Service ID 1"},
                       {"service": "Service ID 2"},
                       {"service": "Service ID 1"},
                       ...
                     ]
    :return: Dictionary with:
             {
                 "status": "success",
                 "total_price": float,
                 "total_duration": float,
                 "applied_modifiers": list
             }
             or in case of an error:
             {
                 "status": "error",
                 "message": "Error details..."
             }
    """
    try:
        _validate_required_params(car_wash, car, services)
        services_aggregated = _validate_and_aggregate_services(services)
        service_counter = _validate_and_aggregate_services_counter(services)

        # 1. Check and cache valid services
        valid_service_ids = _get_valid_services(list(service_counter.keys()))

        # 2. Get Car body type (with caching)
        car_body_type = _get_car_body_type(car)

        # 3. Fetch service docs and prices
        service_docs = _get_service_docs(valid_service_ids)
        service_prices = _get_service_prices(valid_service_ids, car_body_type)

        # 4. Calculate totals
        final_total, total_duration, applied_modifiers, applied_custom_prices = _calculate_totals(
            service_counter, service_docs, service_prices, car_body_type, services_aggregated
        )

        return {
            "status": "success",
            "total_price": final_total,
            "total_duration": total_duration,
            "applied_modifiers": applied_modifiers,
            "applied_custom_prices": applied_custom_prices
        }
    except frappe.ValidationError as ve:
        frappe.log_error(message=ve.message, title="Price and Duration Calculation Validation Error")
        return {
            "status": "error",
            "message": ve.message
        }
    except Exception as e:
        frappe.log_error(message=str(e), title="Price and Duration Calculation Error")
        return {
            "status": "error",
            "message": str(e)
        }


def _validate_required_params(car_wash: str, car: str, services: List[Dict[str, Any]]) -> None:
    """Validate presence of required parameters."""
    if not all([car_wash, car, services]):
        frappe.throw(_("Missing required parameters. Please provide 'car_wash', 'car', and 'services'."))

    if not isinstance(services, list):
        frappe.throw(_("'services' should be a list of service details."))

    if not services:
        frappe.throw(_("At least one service must be provided."))


def _validate_and_aggregate_services_counter(services):
    """
    Validate that each service dict has a 'service' key,
    then return a Counter of service IDs (for quantity calculations).
    """
    service_ids = []
    for service in services:
        if isinstance(service,
                      dict) and 'service' in service:  # Ensure it's a dictionary and has the key
            service_ids.append(service['service'])
        else:
            service_ids.append(service.service)

    return Counter(service_ids)

def _validate_and_aggregate_services(services):
    """
    Validate that each service dict has a 'service' key,
    then return a Counter of service IDs (for quantity calculations).
    """
    service_ids = {}
    for service in services:
        if isinstance(service,
                      dict) and 'service' in service:  # Ensure it's a dictionary and has the key
            if 'custom_price' in service and service['custom_price']:
                service_ids[service['service']] = {"custom_price": service['custom_price']}
        else:
            if service.service and service.custom_price:
                service_ids[service.service] = {"custom_price": service.custom_price}

    return service_ids


def _get_valid_services(unique_service_ids: List[str]) -> List[str]:
    """
    Check which service IDs are valid (not disabled or deleted),
    using caching to avoid repeated lookups.
    """
    if not unique_service_ids:
        return []

    cache = frappe.cache()
    sorted_ids = sorted(unique_service_ids)
    cache_key_services = f"valid_car_wash_services:{','.join(sorted_ids)}"

    existing_services = cache.get_value(cache_key_services)
    if existing_services is None:
        existing_services = frappe.get_all(
            "Car wash service",
            filters={"name": ["in", unique_service_ids], "is_disabled": False, "is_deleted": False},
            pluck="name"
        )
        cache.set_value(cache_key_services, existing_services, expires_in_sec=3600)  # Cache for 1 hour

    invalid_services = set(unique_service_ids) - set(existing_services)
    if invalid_services:
        frappe.throw(_("Invalid or inactive services: {0}".format(", ".join(invalid_services))))

    return existing_services


def _get_car_body_type(car: str) -> str:
    """
    Retrieve Car's Body Type from the 'Car wash car' DocType, with caching.
    """
    cache = frappe.cache()
    cache_key_car_body = f"car_body_type:{car}"
    car_body_type = cache.get_value(cache_key_car_body)

    if car_body_type is None:
        car_doc = frappe.get_doc("Car wash car", car)
        car_body_type = car_doc.body_type
        if not car_body_type:
            frappe.throw(_("The selected car does not have a 'Car Body Type' specified."))
        cache.set_value(cache_key_car_body, car_body_type, expires_in_sec=3600)  # Cache for 1 hour

    return car_body_type


def _get_service_docs(service_ids: List[str]) -> Dict[str, Any]:
    """
    Fetch service documents in bulk, returning a dict of service_id -> doc.
    """
    if not service_ids:
        return {}

    service_docs_list = frappe.get_all(
        "Car wash service",
        filters={"name": ["in", service_ids]},
        fields=[
            "name",
            "title",
            "price",
            "duration",
            "price_modifier",
            "price_modifier_type",
            "price_modifier_value",
            "apply_price_modifier_to_order_total",
            "is_price_modifier_active"
        ]
    )
    return {doc.name: doc for doc in service_docs_list}


def _get_service_prices(service_ids: List[str], car_body_type: str) -> Dict[str, float]:
    """
    Fetch all required service prices based on body type, with caching.
    Returns a dict of service_id -> price.
    """
    cache = frappe.cache()
    sorted_ids = sorted(service_ids)
    cache_key_service_prices = f"car_wash_service_prices:{','.join(sorted_ids)}:{car_body_type}"
    service_prices = cache.get_value(cache_key_service_prices)

    if service_prices is None:
        service_price_records = frappe.get_all(
            "Car wash service price",
            filters={
                "base_service": ["in", service_ids],
                "body_type": car_body_type,
                "is_disabled": False,
                "is_deleted": False
            },
            fields=["base_service", "price"]
        )
        service_prices = {record.base_service: record.price for record in service_price_records}
        cache.set_value(cache_key_service_prices, service_prices, expires_in_sec=3600)  # Cache for 1 hour

    return service_prices


def _calculate_totals(
    service_counter: Counter,
    service_docs: Dict[str, Any],
    service_prices: Dict[str, float],
    car_body_type: str,
    services_aggregated: Dict[str, Any]
) -> (float, float, List[Dict[str, Any]], List[Dict[str, Any]]):
    """
    Given the aggregated services (Counter), full service docs, and service prices,
    compute the final total, total duration, and any applied modifiers.
    """
    total_price = 0.0
    total_duration = 0.0
    # These track order-level modifiers
    total_order_modifiers = {
        "add": 0.0,
        "subtract": 0.0,
        "multiply": 1.0,
        "fixed_price": None
    }
    applied_modifiers = []
    applied_custom_prices = []

    for service_id, quantity in service_counter.items():
        service_doc = service_docs.get(service_id)
        if not service_doc:
            frappe.throw(_(f"Service '{service_id}' details could not be retrieved."))

        # Pull price from body-type-specific prices or fallback to service_doc.price
        base_price = service_prices.get(service_id, service_doc.price)
        if base_price is None:
            frappe.throw(_(
                f"Price not defined for service '{service_doc.title}' and Car body type '{car_body_type}', "
                "and no base price is set."
            ))

        if services_aggregated.get(service_id):
            custom_price = services_aggregated.get(service_id)['custom_price']
            if custom_price:
                base_price = custom_price
                applied_custom_prices.append({"service": service_id, "price": custom_price})

        # Calculate aggregated service price
        service_total_price = base_price * quantity
        total_price += service_total_price

        # Ensure correct multiplication for duration
        duration_value = service_doc.duration or 0
        total_duration += duration_value * quantity

        # Apply price modifiers if active and set to apply to total
        if service_doc.is_price_modifier_active and service_doc.price_modifier_type:
            if service_doc.apply_price_modifier_to_order_total:
                _apply_price_modifier(
                    service_doc, quantity, total_order_modifiers, applied_modifiers
                )

    # Apply any order-level modifiers to the final total
    if total_order_modifiers["fixed_price"] is not None:
        final_total = total_order_modifiers["fixed_price"]
        frappe.logger().debug(f"Final total set by Fixed Price: {final_total}")
    else:
        final_total = (
            (total_price + total_order_modifiers["add"] - total_order_modifiers["subtract"])
            * total_order_modifiers["multiply"]
        )
        frappe.logger().debug(f"Final total calculated: {final_total}")

    # Prevent negative total
    if final_total < 0:
        frappe.logger().warning("Final total was negative, setting to 0")
        final_total = 0.0

    return final_total, total_duration, applied_modifiers, applied_custom_prices


def _apply_price_modifier(
    service_doc: Dict[str, Any],
    quantity: int,
    total_order_modifiers: Dict[str, float],
    applied_modifiers: List[Dict[str, Any]]
) -> None:
    """
    Apply a single service's price modifier to the order-level modifiers.
    """
    modifier_type = service_doc.price_modifier_type
    try:
        modifier_value = float(service_doc.price_modifier_value)
    except (ValueError, TypeError):
        frappe.throw(_(f"Invalid modifier value for service '{service_doc.name}'."))

    valid_modifier_types = {
        "Fixed Addition",
        "Fixed Subtraction",
        "Price Doubling",
        "Multiplier",
        "Fixed Price"
    }
    if modifier_type not in valid_modifier_types:
        frappe.throw(_(f"Invalid modifier type: {modifier_type}"))

    if modifier_type == "Fixed Addition":
        added_value = modifier_value * quantity
        total_order_modifiers["add"] += added_value
        applied_modifiers.append({"type": modifier_type, "value": added_value})
    elif modifier_type == "Fixed Subtraction":
        subtracted_value = modifier_value * quantity
        total_order_modifiers["subtract"] += subtracted_value
        applied_modifiers.append({"type": modifier_type, "value": subtracted_value})
    elif modifier_type == "Price Doubling":
        # Doubling can be repeated multiple times
        dbl = (2 ** quantity)
        total_order_modifiers["multiply"] *= dbl
        applied_modifiers.append({"type": modifier_type, "value": dbl})
    elif modifier_type == "Multiplier":
        mult = (modifier_value ** quantity)
        total_order_modifiers["multiply"] *= mult
        applied_modifiers.append({"type": modifier_type, "value": mult})
    elif modifier_type == "Fixed Price":
        # Overrides everything else
        total_order_modifiers["fixed_price"] = modifier_value
        applied_modifiers.append({"type": modifier_type, "value": modifier_value})
