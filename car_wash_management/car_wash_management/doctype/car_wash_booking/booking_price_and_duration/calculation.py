# car_wash/calculation.py

import frappe
from frappe import _
from typing import Dict, Any, List

def calculate_totals(
    counter,
    docs: Dict[str, Any],
    prices: Dict[str, Any],
    tariff_id: str,                # ← было body_type, теперь tariff_id (можно и вовсе убрать)
    custom_map: Dict[str, float],
) -> tuple[...]:
    total_price = 0.0
    total_duration = 0.0
    staff_reward_total = 0.0
    order_mods = {"add": 0.0, "subtract": 0.0, "multiply": 1.0, "fixed_price": None}
    applied_mods, applied_custom = [], []

    for svc_id, qty in counter.items():
        doc = docs.get(svc_id) or frappe.throw(f"Service '{svc_id}' not found.")
        price_info = prices.get(svc_id, {})

        # цена: либо из прайса тарифа, либо базовая из сервиса
        base = price_info.get("price", doc.price)
        if base is None:
            frappe.throw(f"No price for '{doc.title}' in tariff '{tariff_id}'.")

        # staff reward
        raw_reward = price_info.get("staff_reward")
        if raw_reward is None:
            raw_reward = getattr(doc, "staff_reward", base) or base
        reward_per_unit = raw_reward or base
        staff_reward_total += reward_per_unit * qty

        # кастомная цена
        if svc_id in custom_map:
            base = custom_map[svc_id]
            applied_custom.append({"service": svc_id, "price": base})

        total_price += base * qty

        # длительность: приоритет у duration из прайса тарифа
        dur_override = price_info.get("duration")
        unit_duration = (dur_override if dur_override is not None else (doc.duration or 0))
        total_duration += unit_duration * qty

        # модификаторы заказа — без изменений
        if getattr(doc, "is_price_modifier_active", None) and doc.price_modifier_type and doc.apply_price_modifier_to_order_total:
            _apply_price_modifier(doc, qty, order_mods, applied_mods)

    final = order_mods["fixed_price"] if order_mods["fixed_price"] is not None \
        else (total_price + order_mods["add"] - order_mods["subtract"]) * order_mods["multiply"]
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
