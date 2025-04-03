import frappe
from frappe.query_builder.functions import Count
from frappe.query_builder import DocType, Criterion, Case, Field
from frappe.query_builder.functions import Count, Sum
from pypika.terms import Case
from datetime import datetime

# Самые часто заказываемые услуги за период.
@frappe.whitelist()
def get_service_statistics(start_date, end_date, car_wash_id=None, limit=10):
    # Define DocTypes
    AppointmentService = DocType("Car wash appointment service")
    Appointment = DocType("Car wash appointment")
    Service = DocType("Car wash service")

    # Build query using Frappe Query Builder
    query = (
        frappe.qb.from_(AppointmentService)
        .join(Appointment)
        .on(AppointmentService.parent == Appointment.name)  # In Frappe, child tables use the 'parent' field
        .join(Service)
        .on(AppointmentService.service == Service.name)
        .select(
            Service.title.as_("service_title"),
            Count("*").as_("service_count")
        )
        .where(
            (Appointment.creation[start_date:end_date]) &
            (Appointment.is_deleted == 0)
        )
        .groupby(Service.title)
        .orderby(Count("*"), order=frappe.qb.desc)  # Use the actual expression here
        .limit(limit)
    )

    # Add conditional filter for car_wash_id if provided
    if car_wash_id:
        query = query.where(Appointment.car_wash == car_wash_id)

    # Execute query and return results as dictionaries
    return query.run(as_dict=True)

# Услуга, которая принесла больше всего выручки (цена * кол-во оказаний).
@frappe.whitelist()
def get_top_revenue_service(start_date, end_date, car_wash_id=None):
    """
    Returns the service with the highest revenue in the given date range.

    Args:
        start_date (str): Start date in string format
        end_date (str): End date in string format
        car_wash_id (str, optional): Filter by specific car wash

    Returns:
        dict: Service title and total revenue
    """
    # Define DocTypes
    Appointment = DocType("Car wash appointment")
    AppointmentService = DocType("Car wash appointment service")
    Service = DocType("Car wash service")

    # Build the query
    query = (
        frappe.qb.from_(AppointmentService)
        .join(Appointment)
        .on(AppointmentService.parent == Appointment.name)
        .join(Service)
        .on(AppointmentService.service == Service.name)
        .select(
            Service.title.as_("service_title"),
            Sum(
                Case()
                .when(AppointmentService.price.isnull(), 0)
                .else_(AppointmentService.price)
            ).as_("total_revenue")
        )
        .where(Appointment.creation.between(start_date, end_date))
        .where(Appointment.is_deleted == 0)
        .groupby(Service.title)
        .orderby(Sum(
            Case()
            .when(AppointmentService.price.isnull(), 0)
            .else_(AppointmentService.price)
        ), order=frappe.qb.desc)
        .limit(1)
    )

    # Add car_wash filter if provided
    if car_wash_id:
        query = query.where(Appointment.car_wash == car_wash_id)

    # Execute the query
    result = query.run(as_dict=True)

    return result[0] if result else None


# Анализ распределения услуг по длительности (duration).
@frappe.whitelist()
def get_service_statistics(start_date, end_date, car_wash_id=None):
    # Define DocType references
    appointment = DocType("Car wash appointment")
    appointment_service = DocType("Car wash appointment service")
    service = DocType("Car wash service")

    # Build the query using frappe.qb
    query = (
        frappe.qb.from_(appointment_service)
        .join(appointment)
        .on(appointment_service.parent == appointment.name)
        .join(service)
        .on(appointment_service.service == service.name)
        .select(
            service.title.as_("service_title"),
            service.duration.as_("planned_duration"),
            Count(appointment_service.name).as_("service_count")
        )
        .where(
            (appointment.creation.between(start_date, end_date)) &
            (appointment.is_deleted == 0)
        )
        .groupby(
            service.title,
            service.duration
        )
        .orderby(
            Count(appointment_service.name).as_("service_count"), order=frappe.qb.desc
        )
    )

    # Add optional car_wash filter if provided
    if car_wash_id:
        query = query.where(appointment.car_wash == car_wash_id)

    # Execute the query and return results
    return query.run(as_dict=True)


# Какие услуги чаще заказывают утром/вечером, и т.д.
@frappe.whitelist()
def get_service_usage_by_time_of_day_sql(start_date, end_date, car_wash_id=None):
    """
    This function uses raw SQL to get a count of services grouped by service title and time of day.

    Args:
        start_date: Start date for filtering appointments
        end_date: End date for filtering appointments
        car_wash_id: Optional ID of the car wash to filter by

    Returns:
        List of dictionaries containing service title, time of day, and count
    """
    # Build the WHERE clause for car_wash filtering
    car_wash_filter = ""
    values = {
        "start_date": start_date,
        "end_date": end_date
    }

    if car_wash_id:
        car_wash_filter = "AND a.car_wash = %(car_wash_id)s"
        values["car_wash_id"] = car_wash_id

    # Execute SQL query
    result = frappe.db.sql(
        f"""
        SELECT s.title AS service_title,
               CASE
                 WHEN HOUR(a.starts_on) BETWEEN 6 AND 11 THEN 'morning'
                 WHEN HOUR(a.starts_on) BETWEEN 12 AND 17 THEN 'day'
                 WHEN HOUR(a.starts_on) BETWEEN 18 AND 22 THEN 'evening'
                 ELSE 'night'
               END AS time_of_day,
               COUNT(*) AS count_services
          FROM `tabCar wash appointment service` AS asrv
          JOIN `tabCar wash appointment` AS a ON asrv.parent = a.name
          JOIN `tabCar wash service` AS s ON asrv.service = s.name
         WHERE a.starts_on BETWEEN %(start_date)s AND %(end_date)s
           AND a.is_deleted = 0
           {car_wash_filter}
         GROUP BY s.title, time_of_day
         ORDER BY count_services DESC
         LIMIT 20
        """,
        values=values,
        as_dict=1
    )

    return result

from frappe.query_builder.functions import GroupConcat

# Анализ 'корзины' услуг: какие услуги часто покупаются вместе.
@frappe.whitelist()
def get_appointments_with_services(start_date, end_date, car_wash_id=None):
    """
    Retrieve appointments with concatenated service lists using Frappe Query Builder.

    Args:
        start_date (str): Start date for filtering appointments.
        end_date (str): End date for filtering appointments.
        car_wash_id (str, optional): Optional car wash ID filter.

    Returns:
        List[dict]: List of dictionaries containing appointment_id and services_list.
    """
    # Define DocTypes
    AppointmentService = DocType("Car wash appointment service")
    Appointment = DocType("Car wash appointment")
    Service = DocType("Car wash service")

    # Build the query
    query = (
        frappe.qb.from_(AppointmentService)
        .join(Appointment).on(Appointment.name == AppointmentService.parent)
        .join(Service).on(Service.name == AppointmentService.service)
        .select(
            Appointment.name.as_("appointment_id"),
            GroupConcat(Service.title, ', ').as_("services_list")
        )
        .where(Appointment.creation.between(start_date, end_date))
        .where(Appointment.is_deleted == 0)
        .groupby(Appointment.name)
    )

    # Apply optional car_wash_id filter
    if car_wash_id:
        query = query.where(Appointment.car_wash == car_wash_id)

    # Execute the query and return results
    return query.run(as_dict=True)

# Возвращает услуги, которые заказывали реже, чем threshold раз.
@frappe.whitelist()
def get_underused_services(start_date, end_date, car_wash_id=None, threshold=5):
    """
    Retrieves car wash services that have been used less than a specified threshold
    during the given date range.

    Args:
        start_date (str): Start date in the format 'YYYY-MM-DD'
        end_date (str): End date in the format 'YYYY-MM-DD'
        car_wash_id (str, optional): ID of the car wash to filter by
        threshold (int, optional): Usage count threshold

    Returns:
        list: List of dictionaries containing service id, title, and usage count
    """
    # Define the DocTypes we'll be using
    service = DocType("Car wash service")
    appt_service = DocType("Car wash appointment service")
    appointment = DocType("Car wash appointment")

    # Build the query using frappe.qb
    query = (
        frappe.qb.from_(service)
        .left_join(appt_service)
        .on(service.name == appt_service.service)
        .left_join(appointment)
        .on(appointment.name == appt_service.parent)
        .select(
            service.name.as_("id"),
            service.title,
            Count(appt_service.name).as_("usage_count")
        )
        .where(
            # Use Criterion.any to handle the OR condition
            Criterion.any([
                Criterion.all([
                    appointment.creation.between(start_date, end_date),
                    appointment.is_deleted == 0
                ]),
                appointment.name.isnull()
            ])
        )
        .groupby(service.name, service.title)
    )

    # Add car_wash_id filter if provided
    if car_wash_id:
        query = query.where(service.car_wash == car_wash_id)

    # Note: frappe.qb doesn't directly support HAVING, so we'll apply it after getting results
    results = query.run(as_dict=True)

    # Filter results based on the usage_count threshold
    filtered_results = [r for r in results if r.usage_count < threshold]

    return filtered_results
