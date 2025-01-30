import frappe
from frappe import _

@frappe.whitelist(allow_guest=True)
def get_booking_price_and_duration(car_wash, car, services):
    """
    Calculates the total price and total duration for a Car Wash Booking based on selected services and car body type.

    **Parameters:**
    - `car_wash` (str): Name (ID) of the Car Wash (Link to Car wash DocType).
    - `car` (str): Name (ID) of the Car (Link to Car wash car DocType).
    - `services` (list of dict): List of services with details.
        Example:
        [
            {"service": "Service ID 1"},
            {"service": "Service ID 2"},
            {"service": "Service ID 1"},
            ...
        ]

    **Returns:**
    - `dict`: Total price and total duration.
    """
    try:
        # 1. Validate required parameters
        if not all([car_wash, car, services]):
            frappe.throw(_("Missing required parameters. Please provide 'car_wash', 'car', and 'services'."))

        # 2. Validate services
        if not isinstance(services, list):
            frappe.throw(_("'services' should be a list of service details."))

        if not services:
            frappe.throw(_("At least one service must be provided."))

        service_ids = [service.get("service") for service in services]
        if not all(service_ids):
            frappe.throw(_("Each service entry must include a 'service' field."))

        # 3. Aggregate services to count quantities
        from collections import Counter
        service_counter = Counter(service_ids)

        unique_service_ids = list(service_counter.keys())

        # Initialize cache
        cache = frappe.cache()

        # 4. Validate if services exist using caching
        sorted_service_ids = sorted(unique_service_ids)
        cache_key_services = f"valid_car_wash_services:{','.join(sorted_service_ids)}"
        existing_services = cache.get_value(cache_key_services)

        if not existing_services:
            existing_services = frappe.get_all(
                "Car wash service",
                filters={"name": ["in", unique_service_ids], "is_disabled": False, "is_deleted": False},
                pluck="name"
            )
            cache.set_value(cache_key_services, existing_services, expires_in_sec=3600)  # Кэшируем на 1 час

        invalid_services = set(unique_service_ids) - set(existing_services)
        if invalid_services:
            frappe.throw(_("Invalid or inactive services: {0}".format(", ".join(invalid_services))))

        # 5. Retrieve Car's Body Type with caching
        cache_key_car_body = f"car_body_type:{car}"
        car_body_type = cache.get_value(cache_key_car_body)

        if car_body_type is None:
            car_doc = frappe.get_doc("Car wash car", car)
            car_body_type = car_doc.body_type
            if not car_body_type:
                frappe.throw(_("The selected car does not have a 'Car Body Type' specified."))
            cache.set_value(cache_key_car_body, car_body_type, expires_in_sec=3600)  # Кэшируем на 1 час

        # 6. Fetch all required service documents in bulk with caching
        # cache_key_service_docs = f"car_wash_service_docs:{','.join(sorted_service_ids)}"
        # service_docs = cache.get_value(cache_key_service_docs)

        # if not service_docs:
        service_docs_list = frappe.get_all(
            "Car wash service",
            filters={"name": ["in", unique_service_ids]},
            fields=["name", "title", "price", "duration",
                    "price_modifier", "price_modifier_type", "price_modifier_value",
                    "apply_price_modifier_to_order_total", "is_price_modifier_active"]
        )
        # Преобразуем список словарей в словарь для быстрого доступа
        service_docs = {doc.name: doc for doc in service_docs_list}
            # cache.set_value(cache_key_service_docs, service_docs, expires_in_sec=3600)  # Кэшируем на 1 час

        # 7. Fetch all required service prices based on body type in bulk with caching
        cache_key_service_prices = f"car_wash_service_prices:{','.join(sorted_service_ids)}:{car_body_type}"
        service_prices = cache.get_value(cache_key_service_prices)

        if service_prices is None:
            service_price_records = frappe.get_all(
                "Car wash service price",
                filters={
                    "base_service": ["in", unique_service_ids],
                    "body_type": car_body_type,
                    "is_disabled": False,
                    "is_deleted": False
                },
                fields=["base_service", "price"]
            )
            # Создаем словарь для быстрого доступа
            service_prices = {record.base_service: record.price for record in service_price_records}
            cache.set_value(cache_key_service_prices, service_prices, expires_in_sec=3600)  # Кэшируем на 1 час

        total_price = 0
        total_duration = 0
        total_order_modifiers = {
            "add": 0,
            "subtract": 0,
            "multiply": 1,
            "fixed_price": None
        }
        applied_modifiers = []

        # 8. Итерация через агрегированные услуги для расчета итогов
        for service_id, quantity in service_counter.items():
            service_doc = service_docs.get(service_id)
            if not service_doc:
                frappe.throw(_(
                    "Service '{0}' details could not be retrieved.".format(service_id)
                ))

            # Получение цены из кэша или базовой цены
            price = service_prices.get(service_id, service_doc.price)
            if price is None:
                frappe.throw(_(
                    "Price not defined for service '{0}' and Car body type '{1}', and no base price is set."
                    .format(service_doc.title, car_body_type)
                ))

            # Вычисление общей стоимости и длительности
            service_total_price = price * quantity
            total_price += service_total_price
            total_duration += service_doc.duration or 0 * quantity  # Предполагается, что duration в минутах или другой подходящей единице

            # Обработка модификаторов цены, если они активны
            if service_doc.is_price_modifier_active and service_doc.price_modifier_type:
                if service_doc.apply_price_modifier_to_order_total:
                    modifier_type = service_doc.price_modifier_type
                    try:
                        modifier_value = float(service_doc.price_modifier_value)
                    except (ValueError, TypeError):
                        frappe.throw(_("Invalid modifier value for service '{0}'.".format(service_id)))

                    # Проверка на допустимые типы модификаторов
                    valid_modifier_types = ["Fixed Addition", "Fixed Subtraction", "Price Doubling", "Multiplier", "Fixed Price"]
                    if modifier_type not in valid_modifier_types:
                        frappe.throw(_("Invalid modifier type: {0}".format(modifier_type)))

                    if modifier_type == "Fixed Addition":
                        total_order_modifiers["add"] += modifier_value * quantity
                        applied_modifiers.append({"type": modifier_type, "value": modifier_value * quantity})
                    elif modifier_type == "Fixed Subtraction":
                        total_order_modifiers["subtract"] += modifier_value * quantity
                        applied_modifiers.append({"type": modifier_type, "value": modifier_value * quantity})
                    elif modifier_type == "Price Doubling":
                        total_order_modifiers["multiply"] *= 2 ** quantity
                        applied_modifiers.append({"type": modifier_type, "value": 2 ** quantity})
                    elif modifier_type == "Multiplier":
                        total_order_modifiers["multiply"] *= modifier_value ** quantity
                        applied_modifiers.append({"type": modifier_type, "value": modifier_value ** quantity})
                    elif modifier_type == "Fixed Price":
                        total_order_modifiers["fixed_price"] = modifier_value
                        applied_modifiers.append({"type": modifier_type, "value": modifier_value})

        # 9. Применение модификаторов к общей сумме заказа
        if total_order_modifiers["fixed_price"] is not None:
            final_total = total_order_modifiers["fixed_price"]
            frappe.logger().debug(f"Final total set by Fixed Price: {final_total}")
        else:
            final_total = (total_price + total_order_modifiers["add"] - total_order_modifiers["subtract"]) * total_order_modifiers["multiply"]
            frappe.logger().debug(f"Final total calculated: {final_total}")

        # Защита от отрицательной итоговой суммы
        if final_total < 0:
            frappe.logger().warning("Final total was negative, set to 0")
            final_total = 0  # Устанавливаем минимум 0

        return {
            "status": "success",
            "total_price": final_total,
            "total_duration": total_duration,
            "applied_modifiers": applied_modifiers  # Добавлено для отладки
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
