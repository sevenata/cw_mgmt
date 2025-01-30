import frappe
from frappe.model.document import Document
from frappe.utils import today, now_datetime

class Carwashbooking(Document):
    def before_insert(self):
        if not self.car_wash:
            frappe.throw(_("Car Wash is required"))

        max_num = frappe.db.sql(
            """
            SELECT CAST(MAX(num) AS SIGNED) FROM `tabCar wash booking`
            WHERE DATE(creation) = %s AND car_wash = %s
            """,
            (today(), self.car_wash),
        )

        self.num = (max_num[0][0] or 0) + 1

        # Set confirmation statuses based on source_type
        if self.source_type in ["TelegramMiniApp", "TelegramBot"]:
            self.user_confirmation_status = "Pending"
            self.car_wash_confirmation_status = "Pending"
        else:
            self.user_confirmation_status = "Not applicable"
            self.car_wash_confirmation_status = "Not applicable"

    def validate(self):
        price_and_duration = get_booking_price_and_duration(self.car_wash, self.car, self.services)
        self.services_total = price_and_duration["total_price"]
        self.duration_total = price_and_duration["total_duration"]

        if self.payment_status == "Paid" and self.payment_type and not self.payment_received_on:
            self.payment_received_on = now_datetime()

        # Handle has_appointment
        if self.appointment:
            self.has_appointment = True
        else:
            self.has_appointment = False

        update_cars_in_queue(self)

import frappe
from frappe import _
from frappe.utils import now_datetime, today
from frappe.model.document import Document

@frappe.whitelist(allow_guest=False)
def create_car_wash_booking(
    car_wash,
    customer,
    car,
    services,
    source_type
):
    """
    Creates a new Car Wash Booking with service prices based on Car body type.

    **Parameters:**
    - `car_wash` (str): Name (ID) of the Car Wash (Link to Car wash DocType).
    - `customer` (str): Name (ID) of the Customer (Link to Car wash client DocType).
    - `car` (str): Name (ID) of the Car (Link to Car wash car DocType).
    - `services` (list of dict): List of services with details.
        Example:
        [
            {
                "service": "Service ID",
                "quantity": 1
            },
            ...
        ]
    - `source_type` (str): Source of the booking. Options: "Direct", "WebPanel", "TelegramMiniApp", "TelegramBot".

    **Returns:**
    - `dict`: Success or error message along with booking details.

    **Example Call:**
    Refer to the [Usage Examples](#6-usage-examples) section.
    """
    try:
        # 1. Validate required parameters
        if not all([car_wash, customer, car, services, source_type]):
            frappe.throw(_("Missing required parameters. Please provide all mandatory fields."))

        # 2. Validate source_type
        valid_source_types = ["Direct", "WebPanel", "TelegramMiniApp", "TelegramBot"]
        if source_type not in valid_source_types:
            frappe.throw(_(
                "Invalid source_type. Allowed values are: {0}".format(", ".join(valid_source_types))
            ))

        # 3. Validate services
        if not isinstance(services, list):
            frappe.throw(_("Services should be a list of service details."))

        if not services:
            frappe.throw(_("At least one service must be provided."))

        service_ids = [service.get("service") for service in services]
        if not all(service_ids):
            frappe.throw(_("Each service entry must include a 'service' field."))

        # 4. Validate if services exist
        existing_services = frappe.get_all("Car wash service", filters={"name": ["in", service_ids]}, pluck="name")
        invalid_services = set(service_ids) - set(existing_services)
        if invalid_services:
            frappe.throw(_("Invalid services: {0}".format(", ".join(invalid_services))))

        # 5. Retrieve Car's Body Type
        car_doc = frappe.get_doc("Car wash car", car)
        car_body_type = car_doc.body_type
        if not car_body_type:
            frappe.throw(_("The selected car does not have a 'Car Body Type' specified."))

        # 6. Create a new Carwashbooking document
        booking = frappe.get_doc({
            "doctype": "Car wash booking",
            "car_wash": car_wash,
            "customer": customer,
            "car": car,
            "source_type": source_type
            # Optional fields are omitted as per requirements
        })

        # 7. Append services to the child table with dynamic pricing
        for service in services:
            service_id = service.get("service")
            quantity = service.get("quantity", 1)  # Default quantity to 1 if not provided

            # Fetch service details
            service_doc = frappe.get_doc("Car wash service", service_id)

            # Fetch service price based on Car's body type
            service_price_doc = frappe.get_all(
                "Car wash service price",
                filters={
                    "base_service": service_id,
                    "body_type": car_body_type,
                    "is_disabled": False,
                    "is_deleted": False
                },
                limit=1,
                fields=["price"]
            )

            if service_price_doc:
                price = service_price_doc[0].price
            else:
                # Fallback to base service price if specific price not found
                price = service_doc.price
                if not price:
                    frappe.throw(_(
                        "Price not defined for service '{0}' and Car body type '{1}', and no base price is set."
                        .format(service_doc.title, car_body_type)
                    ))

            # Append to child table
            service_row = booking.append("services", {})
            service_row.service = service_doc.name
            service_row.service_name = service_doc.title
            service_row.duration = service_doc.duration
            service_row.price = price
            service_row.car_wash = service_doc.car_wash
            service_row.quantity = quantity

        # 8. Insert the document
        booking.insert(ignore_permissions=False)  # Enforce permissions

        # 9. Commit the transaction
        frappe.db.commit()

        return {
            "status": "success",
            "message": _("Car wash booking created successfully."),
            "booking": booking.as_dict()
        }

    except frappe.ValidationError as ve:
        frappe.log_error(message=ve.message, title="Car Wash Booking Validation Error")
        return {
            "status": "error",
            "message": ve.message
        }
    except Exception as e:
        frappe.log_error(message=str(e), title="Car Wash Booking Creation Error")
        return {
            "status": "error",
            "message": _("An unexpected error occurred while creating the booking.")
        }

import frappe
from frappe.utils import now_datetime, today
from frappe.model.document import Document

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
                filters={"name": ["in", unique_service_ids]},
                pluck="name"
            )
            cache.set_value(cache_key_services, existing_services, expires_in_sec=3600)  # Кэшируем на 1 час

        invalid_services = set(unique_service_ids) - set(existing_services)
        if invalid_services:
            frappe.throw(_("Invalid services: {0}".format(", ".join(invalid_services))))

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
        cache_key_service_docs = f"car_wash_service_docs:{','.join(sorted_service_ids)}"
        service_docs = cache.get_value(cache_key_service_docs)

        if not service_docs:
            service_docs_list = frappe.get_all(
                "Car wash service",
                filters={"name": ["in", unique_service_ids]},
                fields=["name", "title", "price", "duration"]
            )
            # Преобразуем список словарей в словарь для быстрого доступа
            service_docs = {doc.name: doc for doc in service_docs_list}
            cache.set_value(cache_key_service_docs, service_docs, expires_in_sec=3600)  # Кэшируем на 1 час

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

        # 8. Итерация через агрегированные услуги для расчета итогов
        for service_id, quantity in service_counter.items():
            service_doc = service_docs.get(service_id)
            if not service_doc:
                frappe.throw(_(
                    "Service '{0}' details could not be retrieved.".format(service_id)
                ))

            # Получение цены из кэша или базовой цены
            price = service_prices.get(service_id, service_doc.price)
            if not price:
                frappe.throw(_(
                    "Price not defined for service '{0}' and Car body type '{1}', and no base price is set."
                    .format(service_doc.title, car_body_type)
                ))

            # Вычисление общей стоимости и длительности
            total_price += price * quantity
            total_duration += service_doc.duration * quantity  # Предполагается, что duration в минутах или другой подходящей единице

        return {
            "status": "success",
            "total_price": total_price,
            "total_duration": total_duration
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

def update_cars_in_queue(doc):
    """
    Increments `cars_in_queue` in `Car Wash Availability` when `has_appointment`
    changes from False to True in `Car Wash Booking`.
    """
    if doc.is_new():
        try:
            update_queue_num(doc)
        except frappe.DoesNotExistError:
            create_availability(doc)
        return

    # Fetch the previous state of the document
    previous_doc = frappe.get_doc("Car wash booking", doc.name)

    # Check if has_appointment changed from False → True
    if not previous_doc.has_appointment and doc.has_appointment:

        # Fetch the corresponding Car Wash Availability document
        try:
            update_queue_num(doc)
        except frappe.DoesNotExistError:
            create_availability(doc)
            return  # If the document doesn't exist, safely exit

def get_cars_in_queue(doc):
    return frappe.db.count("Car wash booking", {"has_appointment": False,"car_wash": doc.car_wash})

def update_queue_num(doc):
    availability_doc = frappe.get_doc("Car wash availability", doc.car_wash)
    availability_doc.cars_in_queue = get_cars_in_queue(doc)
    availability_doc.save(ignore_permissions=True)

def create_availability(doc):
    boxes_count = frappe.db.count('Car wash box', {'car_wash': doc.car_wash})
    cars_in_queue = get_cars_in_queue(doc)
    availability_doc = frappe.get_doc({
        "doctype": "Car wash availability",
        "car_wash": doc.car_wash,
        "boxes_count": boxes_count,
        "cars_in_boxes": 0,
        "cars_in_queue": cars_in_queue,
        "is_working_now": 1
    })
    availability_doc.insert(ignore_permissions=True)
