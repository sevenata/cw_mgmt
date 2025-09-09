# auto_discounts.py
"""
Module for handling automatic discounts in car wash booking system.
Provides logic for finding, validating and applying auto discounts with caching.
"""

import frappe
from typing import Dict, Any, List, Optional
from frappe.utils import now_datetime, getdate, flt


def get_applicable_auto_discounts_cached(
    car_wash: str,
    customer: str,
    services: list,
    services_total: float,
    cache_ttl_sec: int = 300,  # 5 минут кэш
    force_refresh: bool = False
) -> List[Dict[str, Any]]:
    """
    Get applicable auto discounts with caching

    Args:
        car_wash: Car wash ID
        customer: Customer ID
        services: List of services
        services_total: Total amount of services
        cache_ttl_sec: Cache TTL in seconds
        force_refresh: Force cache refresh

    Returns:
        List of applicable auto discounts
    """
    # Проверяем наличие фичи promo у мойки
    car_wash_doc = frappe.get_doc("Car wash", car_wash)
    has_promo_feature = car_wash_doc.has_journal_feature("promo")
    
    if not has_promo_feature:
        return []

    # Create cache key
    service_ids = []
    for service in services:
        if isinstance(service, dict):
            service_ids.append(service.get("service_id", ""))
        else:
            service_ids.append(str(service))

    services_key = "|".join(sorted(service_ids))
    cache_key = f"auto_discounts:v1:{car_wash}:{customer}:{services_key}:{services_total}:ttl={cache_ttl_sec}"

    if not force_refresh:
        cached = frappe.cache().get_value(cache_key)
        if cached:
            return frappe.parse_json(cached)

    # Get applicable discounts
    applicable_discounts = _get_applicable_auto_discounts(
        car_wash=car_wash,
        customer=customer,
        services=services,
        services_total=services_total,
        force_refresh=force_refresh
    )

    # Cache results
    frappe.cache().set_value(cache_key, applicable_discounts, expires_in_sec=cache_ttl_sec)

    return applicable_discounts


def _get_applicable_auto_discounts(
    car_wash: str,
    customer: str,
    services: list,
    services_total: float,
    force_refresh: bool = False
) -> List[Dict[str, Any]]:
    """
    Internal method to get applicable auto discounts
    """
    # Get active auto discounts for this car wash
    discounts = frappe.get_all(
        "Car wash auto discount",
        filters={
            "car_wash": car_wash,
            "is_active": 1,
            "is_deleted": 0
        },
        order_by="priority asc"
    )

    print("discounts", discounts)

    if not discounts:
        return []

    # Get customer statistics with caching
    customer_stats = _get_customer_stats_cached(customer, car_wash, force_refresh=force_refresh)

    applicable_discounts = []

    for discount_data in discounts:
        discount = frappe.get_doc("Car wash auto discount", discount_data.name)

        print("discount", discount)

        # Check if discount is valid for current date
        if not discount.is_valid_for_date():
            print("discount is not valid for current date")
            continue

        # Check minimum order amount
        if discount.minimum_order_amount and services_total < discount.minimum_order_amount:
            print("discount is not valid for minimum order amount")
            continue

        # Check if condition is met
        if not discount.is_condition_met(customer_stats, services):
            print("customer_stats", customer_stats)
            print("services", services)
            print("discount is not valid for condition")
            continue

        # Check if applicable to current services
        if not discount.is_applicable_to_services(services):
            print("discount is not valid for applicable to services")
            continue

        # Check usage limit per customer
        if discount.usage_limit_per_customer:
            print("discount is not valid for usage limit per customer")
            usage_count = _get_customer_discount_usage_count(customer, discount.name)
            if usage_count >= discount.usage_limit_per_customer:
                print("discount is not valid for usage limit per customer")
                continue

        print("discount is valid")

        # Calculate discount amount
        service_discount = discount.calculate_discount_amount(services_total)

        print("service_discount", service_discount)

        # Prepare rules snapshot (rules-based conditions)
        try:
            rules_snapshot = [{
                "rule_type": r.rule_type,
                "operator": r.operator,
                "value": r.value,
                "period": r.period,
                "nth_step": r.nth_step,
                "nth_offset": r.nth_offset,
                "services": [s.service for s in (getattr(r, "services", []) or [])],
            } for r in (discount.rules or [])]
        except Exception:
            rules_snapshot = []

        applicable_discounts.append({
            "discount_id": discount.name,
            "name": discount.name_title,
            "description": discount.description,
            "discount_type": discount.discount_type,
            "discount_value": discount.discount_value,
            "service_discount": service_discount,
            "waive_queue_commission": discount.waive_queue_commission,
            "priority": discount.priority,
            "can_combine_with_promocodes": discount.can_combine_with_promocodes,
            "can_combine_with_other_auto_discounts": discount.can_combine_with_other_auto_discounts,
            "condition_met_details": {
                "rules_logic": discount.rules_logic,
                "rules": rules_snapshot,
            }
        })

    return applicable_discounts


def _get_customer_stats_cached(customer: str, car_wash: str, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Get customer statistics with caching
    """
    try:
        customer_doc = frappe.get_doc("Car wash client", customer)
        return customer_doc.get_statistics(car_wash=car_wash, cache_ttl_sec=1800, force_refresh=1 if force_refresh else 0)
    except:
        # If customer doesn't exist yet, return empty stats (for first time customers)
        return {
            "customer": customer,
            "periods": {
                "month": {"total_appointments": 0, "paid_appointments": 0, "spent_total": 0.0, "avg_ticket": 0.0, "unique_cars": 0, "top_services": [], "by_status": {}},
                "year": {"total_appointments": 0, "paid_appointments": 0, "spent_total": 0.0, "avg_ticket": 0.0, "unique_cars": 0, "top_services": [], "by_status": {}},
                "all_time": {"total_appointments": 0, "paid_appointments": 0, "spent_total": 0.0, "avg_ticket": 0.0, "unique_cars": 0, "top_services": [], "by_status": {}}
            }
        }


def _get_customer_discount_usage_count(customer: str, discount_id: str) -> int:
    """
    Get how many times customer has used this auto discount
    """
    # TODO: Implement usage tracking table if needed
    # For now, return 0 (unlimited usage)
    return 0


def apply_best_auto_discounts(
    applicable_discounts: List[Dict[str, Any]],
    services_total: float,
    commission_amount: float = 0.0,
    allow_combinations: bool = True
) -> Dict[str, Any]:
    """
    Apply the best combination of auto discounts

    Args:
        applicable_discounts: List of applicable discounts
        services_total: Total service amount
        commission_amount: Commission amount
        allow_combinations: Allow combining multiple discounts

    Returns:
        Dictionary with applied discounts and final amounts
    """
    if not applicable_discounts:
        return {
            "applied_discounts": [],
            "total_service_discount": 0.0,
            "commission_waived": 0.0,
            "final_services_total": services_total,
            "final_commission": commission_amount,
            "total_discount": 0.0
        }

    if not allow_combinations or len(applicable_discounts) == 1:
        # Apply only the best (highest priority) discount
        best_discount = applicable_discounts[0]
        return _apply_single_discount(best_discount, services_total, commission_amount)

    # Try to find best combination
    best_result = _apply_single_discount(applicable_discounts[0], services_total, commission_amount)

    if len(applicable_discounts) > 1:
        # Check combinations
        combinable_discounts = [d for d in applicable_discounts if d.get("can_combine_with_other_auto_discounts")]

        if len(combinable_discounts) > 1:
            combination_result = _apply_discount_combination(combinable_discounts, services_total, commission_amount)
            if combination_result["total_discount"] > best_result["total_discount"]:
                best_result = combination_result

    return best_result


def record_auto_discount_usage(
    car_wash: str,
    customer: Optional[str],
    context_type: str,
    context_id: str,
    auto_result: Dict[str, Any]
):
    """Persist auto discount usage history for the applied auto discounts result"""
    if not auto_result or not auto_result.get("applied_discounts"):
        return

    # Проверяем наличие фичи promo у мойки
    car_wash_doc = frappe.get_doc("Car wash", car_wash)
    has_promo_feature = car_wash_doc.has_journal_feature("promo")
    
    if not has_promo_feature:
        return

    print('Try to record')

    applied_discounts: List[Dict[str, Any]] = auto_result.get("applied_discounts", [])
    commission_waived_total = flt(auto_result.get("commission_waived", 0.0))

    # Attribute commission waiver to the first discount that has waive flag
    index_with_waiver = -1
    for idx, d in enumerate(applied_discounts):
        if d.get("waive_queue_commission"):
            index_with_waiver = idx
            break

    for idx, d in enumerate(applied_discounts):
        try:
            commission_waived = commission_waived_total if idx == index_with_waiver else 0.0
            service_discount = flt(d.get("service_discount", 0.0))
            frappe.get_doc({
                "doctype": "Car wash auto discount usage",
                "car_wash": car_wash,
                "customer": customer,
                "context_type": context_type,
                "context_id": context_id,
                "discount_id": d.get("discount_id"),
                "discount_name": d.get("name"),
                "rules_snapshot": frappe.as_json(d.get("condition_met_details")),
                "service_discount": service_discount,
                "commission_waived": commission_waived,
                "total_discount": service_discount + commission_waived,
            }).insert(ignore_permissions=True)
        except Exception as e:
            print("Auto discount usage record failed", e)
            frappe.log_error(frappe.get_traceback(), "Auto discount usage record failed")


def _apply_single_discount(discount: Dict[str, Any], services_total: float, commission_amount: float) -> Dict[str, Any]:
    """Apply single auto discount"""
    service_discount = discount["service_discount"]
    commission_waived = commission_amount if discount["waive_queue_commission"] else 0.0

    final_services_total = max(0, services_total - service_discount)
    final_commission = commission_amount - commission_waived

    return {
        "applied_discounts": [discount],
        "total_service_discount": service_discount,
        "commission_waived": commission_waived,
        "final_services_total": final_services_total,
        "final_commission": final_commission,
        "total_discount": service_discount + commission_waived
    }


def _apply_discount_combination(discounts: List[Dict[str, Any]], services_total: float, commission_amount: float) -> Dict[str, Any]:
    """Apply combination of auto discounts"""
    total_service_discount = 0.0
    commission_waived = 0.0
    applied_discounts = []

    # Sort by priority (best first)
    sorted_discounts = sorted(discounts, key=lambda x: x["priority"])

    for discount in sorted_discounts:
        # Add service discount
        total_service_discount += discount["service_discount"]

        # Check commission waiver (only one discount can waive commission)
        if discount["waive_queue_commission"] and commission_waived == 0:
            commission_waived = commission_amount

        applied_discounts.append(discount)

    # Ensure service discount doesn't exceed services total
    total_service_discount = min(total_service_discount, services_total)

    final_services_total = services_total - total_service_discount
    final_commission = commission_amount - commission_waived

    return {
        "applied_discounts": applied_discounts,
        "total_service_discount": total_service_discount,
        "commission_waived": commission_waived,
        "final_services_total": final_services_total,
        "final_commission": final_commission,
        "total_discount": total_service_discount + commission_waived
    }


def validate_auto_discount_with_promocode(auto_discount_result: Dict[str, Any], promocode_applied: bool) -> bool:
    """
    Check if auto discounts can be combined with promocode

    Args:
        auto_discount_result: Result from apply_best_auto_discounts
        promocode_applied: Whether a promocode is being applied

    Returns:
        True if combination is allowed
    """
    if not promocode_applied or not auto_discount_result.get("applied_discounts"):
        return True

    # Check if all applied auto discounts allow combination with promocodes
    for discount in auto_discount_result["applied_discounts"]:
        if not discount.get("can_combine_with_promocodes"):
            return False

    return True


# Utility function to clear auto discount cache for customer
def clear_customer_auto_discount_cache(customer: str, car_wash: str = None):
    """Clear auto discount cache for customer"""
    pattern = f"auto_discounts:v1:{car_wash or '*'}:{customer}:*"
    frappe.cache().delete_keys(pattern)


# ---- Reusable helpers for recorded auto-discount usage ----
def get_recorded_auto_discount_totals(context_type: str, context_id: str) -> tuple[float, float]:
    """
    Sum recorded auto-discount usage totals for a given context.

    Returns:
        (service_discount_sum, commission_waived_sum)
    """
    try:
        rows = frappe.get_all(
            "Car wash auto discount usage",
            filters={
                "context_type": context_type,
                "context_id": context_id,
                "is_disabled": 0,
            },
            fields=["service_discount", "commission_waived"],
        )
        service_discount_sum = 0.0
        commission_waived_sum = 0.0
        for r in rows:
            service_discount_sum += flt(r.get("service_discount") or 0.0)
            commission_waived_sum += flt(r.get("commission_waived") or 0.0)
        return service_discount_sum, commission_waived_sum
    except Exception:
        return 0.0, 0.0


def apply_recorded_auto_discounts_to_base(
    base_services_total: float,
    base_commission: float,
    context_type: str,
    context_id: str,
) -> dict:
    """
    Convenience helper to apply recorded usage on top of base totals.
    """
    service_discount_sum, commission_waived_sum = get_recorded_auto_discount_totals(context_type, context_id)
    final_services_total = max(0.0, flt(base_services_total) - flt(service_discount_sum))
    final_commission = max(0.0, flt(base_commission) - flt(commission_waived_sum))
    return {
        "final_services_total": final_services_total,
        "final_commission": final_commission,
        "total_discount": flt(service_discount_sum) + flt(commission_waived_sum),
        "service_discount_sum": flt(service_discount_sum),
        "commission_waived_sum": flt(commission_waived_sum),
    }


def delete_recorded_auto_discount_usage(context_type: str, context_id: str) -> None:
    """Delete recorded auto discount usage rows for a context."""
    try:
        frappe.db.delete(
            "Car wash auto discount usage",
            filters={"context_type": context_type, "context_id": context_id},
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Delete auto discount usage failed")


def refresh_recorded_auto_discount_usage(
    context_type: str,
    context_id: str,
    base_services_total: float,
    base_commission: float,
) -> Dict[str, float]:
    """
    Recompute and update recorded usage amounts against new base totals without re-evaluating eligibility.

    Returns dict with aggregated sums: {service_discount_sum, commission_waived_sum, total_discount_sum, updated_count}
    """
    rows = frappe.get_all(
        "Car wash auto discount usage",
        filters={"context_type": context_type, "context_id": context_id},
        fields=["name", "discount_id"],
        order_by="creation asc",
    ) or []

    if not rows:
        return {
            "service_discount_sum": 0.0,
            "commission_waived_sum": 0.0,
            "total_discount_sum": 0.0,
            "updated_count": 0,
        }

    # Determine which discount (first with waive flag) should carry the commission waiver
    index_with_waiver = -1
    discount_docs: List[Optional[Any]] = []
    for idx, r in enumerate(rows):
        try:
            d = frappe.get_doc("Car wash auto discount", r["discount_id"]) if r.get("discount_id") else None
        except Exception:
            d = None
        discount_docs.append(d)
        if index_with_waiver == -1 and d and getattr(d, "waive_queue_commission", 0):
            index_with_waiver = idx

    service_discount_sum = 0.0
    commission_waived_sum = 0.0

    for idx, r in enumerate(rows):
        d = discount_docs[idx]
        if not d:
            # If missing, zero out
            service_discount = 0.0
            commission_waived = 0.0
        else:
            # Recompute service discount from discount config (no rule re-evaluation)
            if getattr(d, "discount_type", "Percentage") == "Percentage":
                service_discount = (flt(base_services_total) * flt(d.discount_value or 0)) / 100.0
            else:
                service_discount = min(flt(d.discount_value or 0), flt(base_services_total))
            commission_waived = flt(base_commission) if (idx == index_with_waiver and getattr(d, "waive_queue_commission", 0)) else 0.0

        total_discount = flt(service_discount) + flt(commission_waived)

        # Update the usage row
        try:
            doc = frappe.get_doc("Car wash auto discount usage", r["name"]) 
            doc.service_discount = service_discount
            doc.commission_waived = commission_waived
            doc.total_discount = total_discount
            doc.save(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Refresh auto discount usage failed: {r['name']}")

        service_discount_sum += service_discount
        commission_waived_sum += commission_waived

    return {
        "service_discount_sum": flt(service_discount_sum),
        "commission_waived_sum": flt(commission_waived_sum),
        "total_discount_sum": flt(service_discount_sum + commission_waived_sum),
        "updated_count": len(rows),
    }
