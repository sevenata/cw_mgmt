import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import Count

# Проверка корреляции между маркой/моделью авто и частотой заказов определённых услуг.
@frappe.whitelist()
def get_service_usage_stats(start_date, end_date, car_wash_id=None):
    # Define DocTypes
    appointment = DocType("Car wash appointment")
    car = DocType("Car wash car")
    car_make = DocType("Car make")
    car_model = DocType("Car model")
    appointment_service = DocType("Car wash appointment service")
    service = DocType("Car wash service")

    # Build query with joins
    query = (
        frappe.qb.from_(appointment)
        .join(car).on(appointment.car == car.name)
        .join(car_make).on(car.make == car_make.name)
        .join(car_model).on(car.model == car_model.name)
        .join(appointment_service).on(appointment.name == appointment_service.parent)  # In child tables, parent refers to the parent document
        .join(service).on(appointment_service.service == service.name)
        .select(
            car_make.name.as_("car_make"),
            car_model.name.as_("car_model"),
            service.title.as_("service_title"),
            Count(appointment_service.name).as_("usage_count")
        )
        .where(appointment.creation[start_date:end_date])
        .where(appointment.is_deleted == 0)
        .groupby(car_make.name, car_model.name, service.title)
        .orderby(Count(appointment_service.name).as_("usage_count"), order=frappe.qb.desc)
        .limit(20)
    )

    # Add car_wash filter if specified
    if car_wash_id:
        query = query.where(appointment.car_wash == car_wash_id)

    # Execute the query
    result = query.run(as_dict=True)
    return result

from frappe.query_builder import DocType
from frappe.query_builder.functions import Count

@frappe.whitelist()
def get_car_model_statistics(start_date, end_date, car_wash_id=None):
    # Define DocTypes
    appointment = DocType("Car wash appointment")
    car = DocType("Car wash car")
    car_make = DocType("Car make")
    car_model = DocType("Car model")

    # Build the query
    query = (
        frappe.qb.from_(appointment)
        .join(car).on(appointment.car == car.name)
        .join(car_make).on(car.make == car_make.name)
        .join(car_model).on(car.model == car_model.name)
        .select(
            car_make.name.as_("car_make"),
            car_model.name.as_("car_model"),
            Count(appointment.name).as_("total_orders")
        )
        .where(
            (appointment.creation.between(start_date, end_date)) &
            (appointment.is_deleted == 0)
        )
        .groupby(car_make.name, car_model.name)
        .orderby(Count(appointment.name).as_("total_orders"), order=frappe.qb.desc)
        .limit(20)
    )

    # Add conditional filter for car_wash_id if provided
    if car_wash_id:
        query = query.where(appointment.car_wash == car_wash_id)

    # Execute the query and return the results
    return query.run(as_dict=True)
