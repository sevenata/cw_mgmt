# car_wash/promocode.py

import frappe
from frappe import _
from typing import Dict, Any, Optional
from datetime import datetime


def validate_and_apply_promocode(
    promocode: str,
    car_wash: str,
    user: str,
    services_total: float,
    commission_amount: float,
    is_time_booking: bool = False,
    services: list = None,
    created_by_admin: bool = False
) -> Dict[str, Any]:
    """
    Validate promocode and calculate discounts.
    
    Args:
        promocode: Promocode string to apply
        car_wash: Car wash ID 
        user: User ID for validation
        services_total: Total cost of services
        commission_amount: Commission amount (0 for admin, 100 for regular users in queue)
        is_time_booking: True if booking for specific time, False for queue
        services: List of services for validation
        created_by_admin: True if booking created by car wash admin
    
    Returns:
    {
        'valid': bool,
        'message': str,
        'promo_type': str,
        'service_discount': float,
        'commission_waived': float,
        'total_discount': float,
        'final_services_total': float,
        'final_commission': float,
        'promo_data': dict
    }
    """
    if not promocode:
        return _create_no_promo_response(services_total, commission_amount)

    # Получаем данные промокода
    promo_doc = _get_promocode_doc(promocode, car_wash)
    if not promo_doc:
        return {
            'valid': False,
            'message': _('Промокод не найден или не действителен для данной автомойки'),
            'service_discount': 0,
            'commission_waived': 0,
            'total_discount': 0,
            'final_services_total': services_total,
            'final_commission': commission_amount
        }

    # Валидация промокода
    validation_result = _validate_promocode(promo_doc, user, services_total)
    if not validation_result['valid']:
        return {
            'valid': False,
            'message': validation_result['message'],
            'service_discount': 0,
            'commission_waived': 0,
            'total_discount': 0,
            'final_services_total': services_total,
            'final_commission': commission_amount
        }

    # Применяем промокод
    return _apply_promocode_discount(
        promo_doc, services_total, commission_amount, is_time_booking, services, created_by_admin
    )


def _create_no_promo_response(services_total: float, commission_amount: float) -> Dict[str, Any]:
    """Create response when no promocode is provided."""
    return {
        'valid': True,
        'message': '',
        'promo_type': None,
        'service_discount': 0,
        'commission_waived': 0,
        'total_discount': 0,
        'final_services_total': services_total,
        'final_commission': commission_amount,
        'promo_data': None
    }


def _get_promocode_doc(promocode: str, car_wash: str) -> Optional[Any]:
    """Get promocode document if valid."""
    try:
        promo_doc = frappe.get_doc("Car wash promo code", {
            'code': promocode,
            'car_wash': car_wash,
            'is_active': 1
        })
        return promo_doc
    except frappe.DoesNotExistError:
        return None


def _validate_promocode(promo_doc: Any, user: str, services_total: float) -> Dict[str, Any]:
    """Validate promocode conditions."""
    today = datetime.now().date()

    # Проверка срока действия
    if promo_doc.valid_from and promo_doc.valid_from > today:
        return {
            'valid': False,
            'message': _('Промокод ещё не действителен. Действует с: {}').format(promo_doc.valid_from)
        }

    if promo_doc.valid_to and promo_doc.valid_to < today:
        return {
            'valid': False,
            'message': _('Срок действия промокода истёк: {}').format(promo_doc.valid_to)
        }

    # Проверка лимита использований
    if promo_doc.usage_limit and promo_doc.used_count >= promo_doc.usage_limit:
        return {
            'valid': False,
            'message': _('Промокод исчерпал лимит использований')
        }

    # Проверка минимальной суммы заказа (только для скидки на услуги)
    if (promo_doc.promo_type in ['Service Discount', 'Combined'] and
        promo_doc.minimum_order_amount and services_total < promo_doc.minimum_order_amount):
        return {
            'valid': False,
            'message': _('Минимальная сумма заказа для промокода: {} тенге').format(promo_doc.minimum_order_amount)
        }

    return {'valid': True, 'message': ''}


def _apply_promocode_discount(
    promo_doc: Any,
    services_total: float,
    commission_amount: float,
    is_time_booking: bool,
    services: list = None,
    created_by_admin: bool = False
) -> Dict[str, Any]:
    """Apply promocode discount based on type."""
    service_discount = 0.0
    commission_waived = 0.0
    
    promo_type = promo_doc.promo_type
    
    # Скидка на услуги
    if promo_type in ['Service Discount', 'Combined']:
        service_discount = _calculate_service_discount(promo_doc, services_total, services)
    
    # Освобождение от комиссии за очередь
    if promo_type in ['Queue Commission Waiver', 'Combined']:
        # Комиссия применяется только если:
        # 1. НЕ бронирование на время (is_time_booking=False)
        # 2. НЕ администратор создает (created_by_admin=False) 
        # 3. Есть комиссия для отмены (commission_amount > 0)
        # 4. Промокод имеет настройку на освобождение от комиссии
        if (not is_time_booking and 
            not created_by_admin and 
            commission_amount > 0 and 
            promo_doc.waive_queue_commission):
            commission_waived = commission_amount

    final_services_total = max(0, services_total - service_discount)
    final_commission = max(0, commission_amount - commission_waived)
    total_discount = service_discount + commission_waived

    return {
        'valid': True,
        'message': _('Промокод успешно применён'),
        'promo_type': promo_type,
        'service_discount': service_discount,
        'commission_waived': commission_waived,
        'total_discount': total_discount,
        'final_services_total': final_services_total,
        'final_commission': final_commission,
        'promo_data': {
            'code': promo_doc.code,
            'title': promo_doc.title,
            'discount_type': getattr(promo_doc, 'discount_type', None),
            'discount_value': getattr(promo_doc, 'discount_value', None)
        }
    }


def _calculate_service_discount(
    promo_doc: Any,
    services_total: float,
    services: list = None
) -> float:
    """Calculate service discount amount."""
    if not hasattr(promo_doc, 'discount_type') or not hasattr(promo_doc, 'discount_value'):
        return 0.0

    # Если указаны применимые услуги, проверяем их
    if promo_doc.applicable_services and services:
        applicable_service_ids = [row.service for row in promo_doc.applicable_services]

        # Рассчитываем сумму только по применимым услугам
        applicable_total = 0.0
        for service in services:
            service_id = service.get('service') if isinstance(service, dict) else getattr(service, 'service', None)
            if service_id in applicable_service_ids:
                # Здесь нужно получить цену услуги - упрощенная версия
                applicable_total = services_total  # В реальном случае нужен более точный расчёт
                break

        if applicable_total == 0:
            return 0.0

        discount_base = applicable_total
    else:
        discount_base = services_total

    if promo_doc.discount_type == 'Percentage':
        discount = discount_base * (promo_doc.discount_value / 100.0)
    else:  # Fixed Amount
        discount = min(promo_doc.discount_value, discount_base)

    return max(0, discount)


def record_promocode_usage(
    promo_code: str,
    mobile_booking_attempt: str,
    user: str,
    promo_result: Dict[str, Any]
) -> None:
    """Record promocode usage for analytics."""
    if not promo_result.get('valid') or not promo_result.get('promo_data'):
        return

    # Создаем запись об использовании промокода
    usage_doc = frappe.get_doc({
        'doctype': 'Car wash promo code usage',
        'promo_code': promo_code,
        'mobile_booking_attempt': mobile_booking_attempt,
        'user': user,
        'promo_type': promo_result['promo_type'],
        'service_discount_amount': promo_result['service_discount'],
        'commission_waived_amount': promo_result['commission_waived'],
        'total_discount_amount': promo_result['total_discount'],
        'original_services_total': promo_result['final_services_total'] + promo_result['service_discount'],
        'original_commission': promo_result['final_commission'] + promo_result['commission_waived'],
        'final_services_total': promo_result['final_services_total'],
        'final_commission': promo_result['final_commission']
    })
    usage_doc.insert(ignore_permissions=True)

    # Увеличиваем счётчик использований промокода
    frappe.db.sql("""
        UPDATE `tabCar wash promo code`
        SET used_count = used_count + 1
        WHERE code = %s
    """, [promo_code])
    frappe.db.commit()
