# car_wash/booking.py

import frappe
from typing import Dict, Any

from .tariffs import (resolve_applicable_tariff, ensure_tariff_valid_for_car_wash)
from .validation import (
    validate_required_params,
    build_service_counter,
    build_custom_price_map,
)
from .repository import (
    get_valid_service_ids,
    get_service_docs,
	get_service_prices_by_tariff,
)
from .calculation import (
    calculate_totals,
)

@frappe.whitelist(allow_guest=True)
def get_booking_price_and_duration(
    car_wash: str,
    car: str,
    services: list,
    tariff: Any # ← НОВЫЙ необязательный параметр
) -> Dict[str, Any]:
    """
    Compute total price & duration for the given car wash booking.

    Если tariff передан, используем его (с валидацией принадлежности мойке и активности).
    Иначе авто-подбираем тариф по мойке (и при необходимости контексту).
    """
    try:
        # Текущая проверка оставлена без изменений (car остаётся required).
        validate_required_params(car_wash, car, services)

        service_counter = build_service_counter(services)
        custom_price_map = build_custom_price_map(services)
        valid_ids = get_valid_service_ids(list(service_counter.keys()))

        # 1) Явно переданный тариф → валидируем, иначе авто-подбор
        if tariff:
            tariff_id = ensure_tariff_valid_for_car_wash(tariff, car_wash)
        else:
            tariff_id = resolve_applicable_tariff(car_wash=car_wash, car=car, services=services)

        # 2) Документы услуг + цены по тарифу
        docs = get_service_docs(valid_ids)
        prices = get_service_prices_by_tariff(valid_ids, tariff_id)

        # 3) Итоги
        total_price, total_duration, modifiers, custom_prices, staff_reward_total = calculate_totals(
            service_counter, docs, prices, tariff_id, custom_price_map
        )

        return {
            "status": "success",
            "total_price": total_price,
            "total_duration": total_duration,
            "staff_reward_total": staff_reward_total,
            "applied_modifiers": modifiers,
            "applied_custom_prices": custom_prices,
            "tariff": tariff_id,  # возвращаем, чтобы UI/аудит видел, что применилось
        }

    except frappe.ValidationError as ve:
        frappe.log_error(ve.message, "Booking Validation Error")
        return {"status": "error", "message": ve.message}

    except Exception as e:
        frappe.log_error(str(e), "Booking Error")
        return {"status": "error", "message": str(e)}
