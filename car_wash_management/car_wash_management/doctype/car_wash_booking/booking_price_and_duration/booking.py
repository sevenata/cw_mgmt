# car_wash/booking.py

import frappe
from typing import Dict, Any, Tuple

from .tariffs import resolve_applicable_tariff
from .validation import (
    validate_required_params,
    build_service_counter,
    build_custom_price_map,
)
from .cache_helpers import (
    _make_service_ids_tuple,
    _cached_get_valid_service_ids,
    _cached_get_service_docs,
    _cached_get_service_prices_by_tariff,
    _ensure_tariff_valid_cached,
)
from .calculation import (
    calculate_totals,
)
from .promocode import (
    validate_and_apply_promocode,
    record_promocode_usage,
)
from .auto_discounts import (
    get_applicable_auto_discounts_cached,
    apply_best_auto_discounts,
    validate_auto_discount_with_promocode,
)

@frappe.whitelist(allow_guest=True)
def get_booking_price_and_duration(
    car_wash: str,
    car: str,
    services: list,
    tariff: Any = None, # ← НОВЫЙ необязательный параметр
    promocode: str = None, # ← Промокод
    user: str = None, # ← DEPRECATED: Пользователь. Если не передан, определяется по car
    is_time_booking: bool = False, # ← Бронирование на время или очередь
    commission_amount: float = 100.0, # ← Размер комиссии за очередь (по умолчанию 100 тенге)
    created_by_admin: bool = True, # ← Создается ли бронирование администратором мойки
    apply_auto_discounts: bool = True, # ← Применять автоматические скидки
    disabled_auto_discounts: list = None, # ← Список ID отключенных автоскидок
    auto_discount_cache_ttl: int = 300 # ← TTL кэша для автоскидок (5 минут)
) -> Dict[str, Any]:
    """
    Compute total price & duration for the given car wash booking with promocode and auto discount support.

    Если tariff передан, используем его (с валидацией принадлежности мойке и активности).
    Иначе авто-подбираем тариф по мойке (и при необходимости контексту).

    Комиссия за очередь:
    - Администратор мойки: комиссия не взимается (created_by_admin=True)
    - Обычный пользователь: комиссия 100 тенге за вставание в очередь (is_time_booking=False)

    Автоматические скидки:
    - Применяются автоматически на основе статистики клиента (apply_auto_discounts=True)
    - Можно отключить отдельные скидки через disabled_auto_discounts
    - Кэшируются для повышения производительности

    Промокод применяется к итоговой стоимости услуг и может освобождать от комиссии за очередь.
    Автоскидки и промокоды могут комбинироваться в зависимости от настроек скидки.
    """
    try:
        # Текущая проверка оставлена без изменений (car остаётся required).
        validate_required_params(car_wash, car, services)

        service_counter = build_service_counter(services)

        # Определяем customer из автомобиля, если user не передан (или пустой)
        resolved_user = user
        if not resolved_user:
            try:
                car_doc = frappe.get_doc("Car wash car", car)
                # попытка взять клиента из стандартного поля car.customer; fallback на client
                resolved_user = getattr(car_doc, "customer", None) or getattr(car_doc, "client", None)
            except Exception:
                resolved_user = None

        # Avoid building custom map if no custom_price entries exist
        custom_price_map = build_custom_price_map(services) if any(
            isinstance(s, dict) and s.get('custom_price') for s in services
        ) else {}

        # Cache-aware resolution of valid ids
        ids_tuple = _make_service_ids_tuple(service_counter)
        valid_ids = list(_cached_get_valid_service_ids(ids_tuple))

        # 1) Явно переданный тариф → валидируем, иначе авто-подбор
        if tariff:
            tariff_id = _ensure_tariff_valid_cached(tariff, car_wash)
        else:
            tariff_id = resolve_applicable_tariff(car_wash=car_wash, car=car, services=services)

        # 2) Документы услуг + цены по тарифу
        ids_tuple = tuple(valid_ids)
        docs = _cached_get_service_docs(ids_tuple)
        prices = _cached_get_service_prices_by_tariff(ids_tuple, tariff_id)

        # 3) Базовые итоги (без промокода)
        base_services_price, total_duration, modifiers, custom_prices, staff_reward_total = calculate_totals(
            service_counter, docs, prices, tariff_id, custom_price_map
        )

        # 4) Расчет комиссии в зависимости от типа пользователя
        actual_commission = 0.0
        if not created_by_admin and not is_time_booking:
            # Комиссия только для обычных пользователей при вставании в очередь
            actual_commission = commission_amount

        # 5) Получение и применение автоматических скидок
        auto_discount_result = {"applied_discounts": [], "total_service_discount": 0.0, "commission_waived": 0.0, "final_services_total": base_services_price, "final_commission": actual_commission, "total_discount": 0.0}

        if apply_auto_discounts and resolved_user:  # Автоскидки применяются только для авторизованных пользователей
            try:
                # Получаем применимые автоскидки
                applicable_auto_discounts = get_applicable_auto_discounts_cached(
                    car_wash=car_wash,
                    customer=resolved_user,
                    services=services,
                    services_total=base_services_price,
                    cache_ttl_sec=auto_discount_cache_ttl,
                    force_refresh=True
                )

                print("car_wash", car_wash)
                print("resolved_user", resolved_user)
                print("services", services)
                print("base_services_price", base_services_price)
                print("auto_discount_cache_ttl", auto_discount_cache_ttl)
                print("force_refresh", True)
                print("applicable_auto_discounts", applicable_auto_discounts)

                # Исключаем отключенные скидки
                if disabled_auto_discounts:
                    applicable_auto_discounts = [
                        discount for discount in applicable_auto_discounts
                        if discount["discount_id"] not in disabled_auto_discounts
                    ]

                # Применяем лучшие автоскидки
                if applicable_auto_discounts:
                    auto_discount_result = apply_best_auto_discounts(
                        applicable_discounts=applicable_auto_discounts,
                        services_total=base_services_price,
                        commission_amount=actual_commission,
                        allow_combinations=True
                    )
            except Exception as e:
                print("Auto discount error: ", e)
                frappe.log_error(f"Auto discount error: {str(e)}", "Auto Discount Error")
                # Продолжаем без автоскидок в случае ошибки

        # Обновляем стоимость после автоскидок
        services_after_auto_discount = auto_discount_result["final_services_total"]
        commission_after_auto_discount = auto_discount_result["final_commission"]

        # 6) Применение промокода
        promo_result = {
            'valid': False,
            'message': '',
            'service_discount': 0.0,
            'commission_waived': 0.0,
            'total_discount': 0.0,
            'final_services_total': services_after_auto_discount,
            'final_commission': commission_after_auto_discount,
        }

        if promocode:
            # Проверяем совместимость автоскидок с промокодом
            can_combine = validate_auto_discount_with_promocode(auto_discount_result, True)

            if can_combine:
                promo_result = validate_and_apply_promocode(
                    promocode=promocode,
                    car_wash=car_wash,
                    user=resolved_user,
                    services_total=services_after_auto_discount,  # Применяем к цене после автоскидок
                    commission_amount=commission_after_auto_discount,
                    is_time_booking=is_time_booking,
                    services=services,
                    created_by_admin=created_by_admin
                )
            else:
                promo_result = {
                    'valid': False,
                    'message': 'Промокод нельзя комбинировать с примененными автоматическими скидками',
                    'service_discount': 0.0,
                    'commission_waived': 0.0,
                    'total_discount': 0.0,
                    'final_services_total': services_after_auto_discount,
                    'final_commission': commission_after_auto_discount,
                }

        # 7) Финальные расчёты с учётом промокода
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

            # Информация об автоматических скидках
            "auto_discounts_applied": len(auto_discount_result["applied_discounts"]) > 0,
            "auto_discounts": {
                "applied_discounts": auto_discount_result["applied_discounts"],
                "total_service_discount": auto_discount_result["total_service_discount"],
                "commission_waived": auto_discount_result["commission_waived"],
                "total_discount": auto_discount_result["total_discount"],
                "services_price_after_auto_discounts": services_after_auto_discount,
                "commission_after_auto_discounts": commission_after_auto_discount
            },

            # Информация о промокоде
            "promocode_applied": promo_result['valid'],
            "promocode_message": promo_result.get('message', ''),
            "promocode_discount": {
                "service_discount": promo_result['service_discount'],
                "commission_waived": promo_result['commission_waived'],
                "total_discount": promo_result['total_discount'],
                "promo_type": promo_result.get('promo_type'),
                "promo_data": promo_result.get('promo_data')
            },

            # Общая информация о скидках
            "total_discounts": {
                "auto_discount_total": auto_discount_result["total_discount"],
                "promocode_total": promo_result['total_discount'],
                "combined_total": auto_discount_result["total_discount"] + promo_result['total_discount']
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
