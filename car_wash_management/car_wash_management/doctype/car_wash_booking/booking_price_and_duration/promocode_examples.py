# car_wash/promocode_examples.py
# Примеры использования промокодов в системе бронирования автомойки

"""
ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ ПРОМОКОДОВ

1. Расчёт стоимости с промокодом при создании бронирования:

from car_wash_management.car_wash_management.doctype.car_wash_booking.booking_price_and_duration.booking import get_booking_price_and_duration

result = get_booking_price_and_duration(
    car_wash="WASH-001",
    car="CAR-001", 
    services=[
        {"service": "SERVICE-001", "quantity": 1},
        {"service": "SERVICE-002", "quantity": 1}
    ],
    promocode="FREEWASH50",
    user="USER-001",
    is_time_booking=False,      # Клиент встает в очередь
    commission_amount=100.0,    # Размер комиссии по умолчанию
    created_by_admin=False      # Создает обычный пользователь (будет комиссия)
)

# Результат:
{
    "status": "success",
    "base_services_price": 2000.0,        # Базовая стоимость услуг
    "final_services_price": 1500.0,       # После применения промокода (25% скидка)
    "commission_amount": 100.0,            # Исходная комиссия
    "final_commission": 0.0,               # После промокода (освобождение от комиссии)
    "total_price": 1500.0,                 # Итого к оплате
    "promocode_applied": True,
    "promocode_message": "Промокод успешно применён",
    "promocode_discount": {
        "service_discount": 500.0,         # Скидка на услуги
        "commission_waived": 100.0,        # Освобождённая комиссия
        "total_discount": 600.0,           # Общая выгода
        "promo_type": "Combined",          # Тип промокода
        "promo_data": {
            "code": "FREEWASH50",
            "title": "Скидка 25% + бесплатная очередь"
        }
    }
}

2. Применение промокода к уже созданной попытке бронирования:

from car_wash_management.car_wash_management.doctype.car_wash_booking.booking_price_and_duration.booking import apply_promocode_to_booking_attempt

result = apply_promocode_to_booking_attempt(
    booking_attempt_id="BOOKING-ATTEMPT-001",
    promocode="FREEQUEUE",
    created_by_admin=True  # Администратор применяет промокод
)

3. Типы промокодов:

   a) Service Discount - скидка только на услуги:
   {
       "promo_type": "Service Discount",
       "discount_type": "Percentage",
       "discount_value": 20.0,
       "minimum_order_amount": 1000.0,
       "applicable_services": [список услуг]
   }

   b) Queue Commission Waiver - освобождение от комиссии за очередь:
   {
       "promo_type": "Queue Commission Waiver", 
       "waive_queue_commission": True
   }

   c) Combined - и скидка, и освобождение:
   {
       "promo_type": "Combined",
       "discount_type": "Fixed Amount",
       "discount_value": 500.0,
       "waive_queue_commission": True
   }

4. Валидация промокодов:

   - Проверка принадлежности мойке
   - Проверка срока действия (valid_from, valid_to)
   - Проверка лимита использований (usage_limit, used_count)
   - Проверка минимальной суммы заказа
   - Проверка активности (is_active)

5. Логика комиссии за очередь:

   - Комиссия применяется только если is_time_booking = False (клиент встает в очередь)
   - Размер комиссии по умолчанию 100 тенге, но можно настроить
   - Администратор мойки: комиссия НЕ взимается (created_by_admin=True)
   - Обычный пользователь: комиссия 100₸ за очередь (created_by_admin=False)
   - Промокод типа "Queue Commission Waiver" или "Combined" может освободить от комиссии

6. Отслеживание использований:

   - Каждое применение промокода записывается в "Car wash promo code usage"
   - Увеличивается счетчик used_count у промокода
   - Сохраняется полная информация о скидке и суммах

ИНТЕГРАЦИЯ С МОБИЛЬНЫМ ПРИЛОЖЕНИЕМ:

При создании car_wash_mobile_booking_attempt нужно:

1. Вызвать get_booking_price_and_duration с промокодом
2. Если промокод валиден, сохранить данные в полях:
   - promo_code_applied
   - promo_code_type  
   - promo_service_discount
   - promo_commission_waived
   - original_services_total
   - original_commission_user

3. Обновить итоговые поля:
   - services_total (после скидки)
   - commission_user (после освобождения)
   - total (общая сумма к оплате)

ДОПОЛНИТЕЛЬНЫЕ ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ:

1. Администратор создает бронирование (без комиссии):

result = get_booking_price_and_duration(
    car_wash="WASH-001",
    car="CAR-001", 
    services=[{"service": "SERVICE-001", "quantity": 1}],
    promocode="SAVE20",           # Промокод на скидку услуг
    user="ADMIN-001",            # Администратор
    is_time_booking=False,       # Очередь
    commission_amount=100.0,     # Размер комиссии (если бы был пользователь)
    created_by_admin=True        # Создает администратор - комиссии НЕТ
)
# Результат: скидка применится к услугам, но комиссии изначально нет

2. Пользователь создает бронирование с промокодом на бесплатную очередь:

result = get_booking_price_and_duration(
    car_wash="WASH-001",
    car="CAR-001", 
    services=[{"service": "SERVICE-001", "quantity": 1}],
    promocode="FREEQUEUE",       # Промокод на бесплатную очередь
    user="USER-001",             # Обычный пользователь
    is_time_booking=False,       # Очередь
    commission_amount=100.0,     # Комиссия за очередь
    created_by_admin=False       # Создает пользователь - ЕСТЬ комиссия
)
# Результат: промокод отменит комиссию 100₸ за очередь

3. Пользователь бронирует на конкретное время (нет комиссии):

result = get_booking_price_and_duration(
    car_wash="WASH-001",
    car="CAR-001", 
    services=[{"service": "SERVICE-001", "quantity": 1}],
    promocode="FREEQUEUE",       # Промокод на бесплатную очередь
    user="USER-001",             # Обычный пользователь
    is_time_booking=True,        # Бронирование на время
    commission_amount=100.0,     # Размер комиссии (не применяется)
    created_by_admin=False       # Создает пользователь
)
# Результат: промокод на очередь не сработает, т.к. это бронирование на время

4. Комбинированный промокод для пользователя:

result = get_booking_price_and_duration(
    car_wash="WASH-001",
    car="CAR-001", 
    services=[{"service": "SERVICE-001", "quantity": 1}],
    promocode="SUPERPROMO",      # Комбинированный промокод
    user="USER-001",             # Обычный пользователь
    is_time_booking=False,       # Очередь
    commission_amount=100.0,     # Комиссия за очередь
    created_by_admin=False       # Создает пользователь
)
# Результат: применится и скидка на услуги, и освобождение от комиссии

МАТРИЦА ПРИМЕНЕНИЯ ПРОМОКОДОВ:

| created_by_admin | is_time_booking | Базовая комиссия | Промокод может отменить комиссию? |
|------------------|-----------------|------------------|-----------------------------------|
| True             | True            | 0₸               | Нет (нет комиссии)                |
| True             | False           | 0₸               | Нет (нет комиссии)                |
| False            | True            | 0₸               | Нет (нет комиссии)                |
| False            | False           | 100₸             | Да (есть комиссия за очередь)     |

ВАЖНО: Промокод на освобождение от комиссии работает только для обычных 
пользователей, которые встают в очередь (не бронируют на время).
"""
