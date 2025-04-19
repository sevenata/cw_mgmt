# car_wash/calculation.py

import frappe
from frappe import _
from typing import Dict, Any, List, Tuple, Union, Optional
from collections import Counter


def calculate_totals(
    counter: Counter[str],
    docs: Dict[str, Any],
    prices: Dict[str, Any],
    body_type: str,
    custom_map: Dict[str, float],
) -> tuple[
    Union[Optional[float], Any], Union[float, Any], list[dict[str, Any]], list[dict[str, Any]],
    Union[float, Any]]:
    total_price = 0.0
    total_duration = 0.0
    staff_reward_total = 0.0
    order_mods = {"add": 0.0, "subtract": 0.0, "multiply": 1.0, "fixed_price": None}
    applied_mods: List[Dict[str, Any]] = []
    applied_custom: List[Dict[str, Any]] = []

    for svc_id, qty in counter.items():
        doc = docs.get(svc_id) or frappe.throw(_(f"Service '{svc_id}' not found."))
        price_info = prices.get(svc_id, {})
        base = price_info.get("price", doc.price)

        raw = price_info.get("staff_reward")
        if raw is None:
            raw = getattr(doc, "staff_reward", base) or base
        reward_per_unit = raw or base

        # now it's safe to multiply
        staff_reward_total += reward_per_unit * qty
        if base is None:
            frappe.throw(_(f"No price for '{doc.title}' on body '{body_type}'."))
        if svc_id in custom_map:
            base = custom_map[svc_id]
            applied_custom.append({"service": svc_id, "price": base})

        total_price += base * qty
        total_duration += (doc.duration or 0) * qty

        if doc.is_price_modifier_active and doc.price_modifier_type and doc.apply_price_modifier_to_order_total:
            _apply_price_modifier(doc, qty, order_mods, applied_mods)

    # apply order‑level mods
    if order_mods["fixed_price"] is not None:
        final = order_mods["fixed_price"]
    else:
        final = (total_price + order_mods["add"] - order_mods["subtract"]) * order_mods["multiply"]

    final = max(final, 0.0)

    return final, total_duration, applied_mods, applied_custom, staff_reward_total


def _apply_price_modifier(
    doc: Any,
    qty: int,
    order_mods: Dict[str, Any],
    applied_mods: List[Dict[str, Any]],
) -> None:
    typ = doc.price_modifier_type
    try:
        val = float(doc.price_modifier_value)
    except (TypeError, ValueError):
        frappe.throw(_(f"Invalid modifier for '{doc.name}'."))
    if typ == "Fixed Addition":
        amt = val * qty
        order_mods["add"] += amt
        applied_mods.append({"type": typ, "value": amt})
    elif typ == "Fixed Subtraction":
        amt = val * qty
        order_mods["subtract"] += amt
        applied_mods.append({"type": typ, "value": amt})
    elif typ == "Price Doubling":
        factor = 2 ** qty
        order_mods["multiply"] *= factor
        applied_mods.append({"type": typ, "value": factor})
    elif typ == "Multiplier":
        factor = val ** qty
        order_mods["multiply"] *= factor
        applied_mods.append({"type": typ, "value": factor})
    elif typ == "Fixed Price":
        order_mods["fixed_price"] = val
        applied_mods.append({"type": typ, "value": val})
    else:
        frappe.throw(_(f"Unknown modifier type '{typ}'."))


def get_services_price_details(
    counter: Counter[str],
    docs: Dict[str, Any],
    prices: Dict[str, float],
    body_type: str,
    custom_map: Dict[str, float],
) -> List[Dict[str, Any]]:
    """
    Return a list of each service with unit_price, total_price, duration, and flags.
    """
    result: List[Dict[str, Any]] = []

    for svc_id, qty in counter.items():
        doc = docs.get(svc_id) or frappe.throw(_(f"Service '{svc_id}' not found."))
        unit = prices.get(svc_id, doc.price)
        if unit is None:
            frappe.throw(_(f"No price for '{doc.title}' on body '{body_type}'."))
        custom_applied = svc_id in custom_map
        if custom_applied:
            unit = custom_map[svc_id]

        total = unit * qty
        duration = (doc.duration or 0) * qty
        is_mod = bool(doc.is_price_modifier_active and doc.price_modifier_type)

        entry = {
            "service_id": svc_id,
            "title": doc.title,
            "quantity": qty,
            "unit_price": unit,
            "total_price": total,
            "duration": duration,
            "is_price_modifier": is_mod,
        }

        # include per‑service staff reward info
        # pick up price‑record reward or doc.reward, defaulting to 0.0
        pr = prices.get(svc_id, {}).get("staff_reward")
        if pr is None:
            pr = getattr(doc, "staff_reward", unit) or unit
        reward = pr
        entry["staff_reward"] = reward
        entry["staff_reward_total"] = reward * qty

        if custom_applied:
            entry["custom_price_applied"] = True

        result.append(entry)

    return result
