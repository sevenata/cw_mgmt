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
from .promocode import (
    validate_and_apply_promocode,
    record_promocode_usage,
)

@frappe.whitelist(allow_guest=True)
def get_booking_price_and_duration(
    car_wash: str,
    car: str,
    services: list,
    tariff: Any = None, # ← НОВЫЙ необязательный параметр
    promocode: str = None, # ← Промокод
    user: str = None, # ← Пользователь для валидации промокода
    is_time_booking: bool = False, # ← Бронирование на время или очередь
    commission_amount: float = 100.0, # ← Размер комиссии за очередь (по умолчанию 100 тенге)
    created_by_admin: bool = True # ← Создается ли бронирование администратором мойки
) -> Dict[str, Any]:
    """
    Compute total price & duration for the given car wash booking with promocode support.

    Если tariff передан, используем его (с валидацией принадлежности мойке и активности).
    Иначе авто-подбираем тариф по мойке (и при необходимости контексту).
    
    Комиссия за очередь:
    - Администратор мойки: комиссия не взимается (created_by_admin=True)
    - Обычный пользователь: комиссия 100 тенге за вставание в очередь (is_time_booking=False)
    
    Промокод применяется к итоговой стоимости услуг и может освобождать от комиссии за очередь.
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

        # 3) Базовые итоги (без промокода)
        base_services_price, total_duration, modifiers, custom_prices, staff_reward_total = calculate_totals(
            service_counter, docs, prices, tariff_id, custom_price_map
        )

        # 4) Расчет комиссии в зависимости от типа пользователя
        actual_commission = 0.0
        if not created_by_admin and not is_time_booking:
            # Комиссия только для обычных пользователей при вставании в очередь
            actual_commission = commission_amount

        # 5) Применение промокода
        promo_result = validate_and_apply_promocode(
            promocode=promocode,
            car_wash=car_wash,
            user=user,
            services_total=base_services_price,
            commission_amount=actual_commission,
            is_time_booking=is_time_booking,
            services=services,
            created_by_admin=created_by_admin
        )

        # 6) Финальные расчёты с учётом промокода
        final_services_price = promo_result['final_services_total']
        final_commission = promo_result['final_commission']
        final_total = final_services_price + final_commission

        response = {
            "status": "success",
            "base_services_price": base_services_price,
            "final_services_price": final_services_price,
            "original_commission": actual_commission,
            "final_commission": final_commission,
            "total_price": final_total,
            "total_duration": total_duration,
            "staff_reward_total": staff_reward_total,
            "applied_modifiers": modifiers,
            "applied_custom_prices": custom_prices,
            "tariff": tariff_id,
            "created_by_admin": created_by_admin,
            "is_time_booking": is_time_booking,
            "promocode_applied": promo_result['valid'],
            "promocode_message": promo_result.get('message', ''),
            "promocode_discount": {
                "service_discount": promo_result['service_discount'],
                "commission_waived": promo_result['commission_waived'],
                "total_discount": promo_result['total_discount'],
                "promo_type": promo_result.get('promo_type'),
                "promo_data": promo_result.get('promo_data')
            }
        }

        return response

    except frappe.ValidationError as ve:
        frappe.log_error(ve.message, "Booking Validation Error")
        return {"status": "error", "message": ve.message}

    except Exception as e:
        frappe.log_error(str(e), "Booking Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def apply_promocode_to_booking_attempt(
    booking_attempt_id: str,
    promocode: str,
    created_by_admin: bool = False
) -> Dict[str, Any]:
    """
    Apply promocode to existing booking attempt.
    Updates the booking attempt with promocode data.
    
    Args:
        booking_attempt_id: ID of the booking attempt
        promocode: Promocode to apply  
        created_by_admin: True if promocode is being applied by admin
    """
    try:
        # Получаем документ booking attempt
        booking_doc = frappe.get_doc("Car wash mobile booking attempt", booking_attempt_id)
        
        # Определяем исходную комиссию в зависимости от того, кто применяет промокод
        original_commission = booking_doc.commission_user
        if created_by_admin and not booking_doc.is_time_booking:
            # Если админ применяет промокод к бронированию обычного пользователя
            # исходная комиссия остается той, что была при создании
            pass  # original_commission остается как есть
        
        # Применяем промокод
        promo_result = validate_and_apply_promocode(
            promocode=promocode,
            car_wash=booking_doc.car_wash,
            user=booking_doc.user,
            services_total=booking_doc.services_total,
            commission_amount=original_commission,
            is_time_booking=booking_doc.is_time_booking,
            services=booking_doc.services,
            created_by_admin=created_by_admin
        )

        if not promo_result['valid']:
            return {
                "status": "error",
                "message": promo_result['message']
            }

        # Обновляем документ
        booking_doc.promo_code_applied = promocode
        booking_doc.promo_code_type = promo_result['promo_type']
        booking_doc.promo_service_discount = promo_result['service_discount']
        booking_doc.promo_commission_waived = promo_result['commission_waived']
        booking_doc.original_services_total = booking_doc.services_total
        booking_doc.original_commission_user = booking_doc.commission_user

        # Пересчитываем итоговые суммы
        booking_doc.services_total = promo_result['final_services_total']
        booking_doc.commission_user = promo_result['final_commission']
        booking_doc.total = promo_result['final_services_total'] + promo_result['final_commission']

        booking_doc.save()

        # Записываем использование промокода
        record_promocode_usage(promocode, booking_attempt_id, booking_doc.user, promo_result)

        return {
            "status": "success",
            "message": _("Промокод успешно применён"),
            "booking_attempt": booking_doc.as_dict(),
            "promocode_discount": {
                "service_discount": promo_result['service_discount'],
                "commission_waived": promo_result['commission_waived'],
                "total_discount": promo_result['total_discount']
            }
        }

    except Exception as e:
        frappe.log_error(str(e), "Promocode Application Error")
        return {"status": "error", "message": str(e)}
