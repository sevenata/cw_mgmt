import frappe
from frappe.query_builder import functions as fn
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import Avg, IfNull, Count, Date
from frappe.query_builder import DocType

# Считает общую выручку по завершённым заказам (servicesTotal + смешанные платежи) за период.
@frappe.whitelist()
def get_total_revenue_qb(start_date, end_date, car_wash_id=None):
    CarWashAppointment = frappe.qb.DocType("Car wash appointment")

    query = (
        frappe.qb.from_(CarWashAppointment)
        .select(fn.IfNull(fn.Sum(CarWashAppointment.services_total), 0).as_("total_revenue"))
        .where(
            (CarWashAppointment.is_deleted == 0) &
            (CarWashAppointment.cancellation_reason.isnull()) &
            (CarWashAppointment.creation[start_date:end_date])
        )
    )

    if car_wash_id:
        query = query.where(CarWashAppointment.car_wash == car_wash_id)

    result = query.run(as_dict=True)
    return result[0].total_revenue if result else 0

# Рассчитывает средний чек (средняя сумма заказа) за указанный период.
@frappe.whitelist()
def get_average_check_qb(start_date, end_date, car_wash_id=None):
    Appointment = DocType("Car wash appointment")

    query = frappe.qb.from_(Appointment)\
        .select(IfNull(Avg(Appointment.services_total), 0).as_("avg_check"))\
        .where(Appointment.creation.between(start_date, end_date))\
        .where(Appointment.is_deleted == 0)\
        .where(Appointment.cancellation_reason.isnull())

    if car_wash_id:
        query = query.where(Appointment.car_wash == car_wash_id)

    result = query.run()
    return result[0][0] if result else 0

# Считает, сколько в среднем длится обслуживание.
@frappe.whitelist()
def get_avg_service_duration(start_date, end_date, car_wash_id=None):
    # Build conditional filter for car_wash
    car_wash_condition = "AND car_wash = %(car_wash_id)s" if car_wash_id else ""

    # Execute query with proper parameter binding
    result = frappe.db.sql("""
        SELECT IFNULL(AVG(TIMESTAMPDIFF(MINUTE, work_started_on, work_ended_on)), 0) AS avg_duration
        FROM `tabCar wash appointment`
        WHERE creation BETWEEN %(start_date)s AND %(end_date)s
          AND is_deleted = 0
          AND work_started_on IS NOT NULL
          AND work_ended_on IS NOT NULL
          {car_wash_condition}
    """.format(car_wash_condition=car_wash_condition), {
        'start_date': start_date,
        'end_date': end_date,
        'car_wash_id': car_wash_id
    }, as_dict=1)

    return result[0].avg_duration if result else 0

# Определяет наиболее загруженные временные промежутки (часы дня).
@frappe.whitelist()
def get_popular_appointment_hours(start_date=None, end_date=None, car_wash_id=None):
    """
    Find the most popular hours for car wash appointments.

    Args:
        start_date: Starting date for analysis period
        end_date: Ending date for analysis period
        car_wash_id: Optional filter for specific car wash location

    Returns:
        List of dicts with hour_slot and count_appointments
    """
    conditions = []

    if start_date and end_date:
        conditions.append("starts_on BETWEEN %(start_date)s AND %(end_date)s")

    conditions.append("is_deleted = 0")

    if car_wash_id:
        car_wash_condition = "car_wash = %(car_wash_id)s"
    else:
        car_wash_condition = "1=1"

    conditions.append(f"({car_wash_condition})")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    query = f"""
        SELECT HOUR(starts_on) AS hour_slot, COUNT(*) AS count_appointments
        FROM `tabCar wash appointment`
        WHERE {where_clause}
        GROUP BY HOUR(starts_on)
        ORDER BY count_appointments DESC
        LIMIT 5
    """

    return frappe.db.sql(
        query,
        {
            "start_date": start_date,
            "end_date": end_date,
            "car_wash_id": car_wash_id
        },
        as_dict=True
    )

# Динамика количества заказов по дням.
@frappe.whitelist()
def get_daily_appointment_counts(start_date, end_date, car_wash_id=None):
    # Reference to the DocType
    appointment = DocType("Car wash appointment")

    # Build the query
    query = (
        frappe.qb.from_(appointment)
        .select(
            Date(appointment.creation).as_("day"),
            Count("*").as_("daily_count")
        )
        .where(
            (appointment.creation.between(start_date, end_date)) &
            (appointment.is_deleted == 0)
        )
    )

    # Add optional car_wash filter
    if car_wash_id:
        query = query.where(appointment.car_wash == car_wash_id)

    # Group by day and order by day ascending
    query = query.groupby(Date(appointment.creation)).orderby("day")

    # Execute the query and return results as dictionaries
    return query.run(as_dict=True)

# Количество заказов, выполненных вне очереди (outOfTurn).
@frappe.whitelist()
def get_out_of_turn_count(start_date, end_date, car_wash_id=None):
    appointment = DocType("Car wash appointment")

    query = (
        frappe.qb.from_(appointment)
        .select(Count("*").as_("oot_count"))
        .where(appointment.creation.between(start_date, end_date))
        .where(appointment.is_deleted == 0)
        .where(appointment.out_of_turn == 1)
    )

    if car_wash_id:
        query = query.where(appointment.car_wash == car_wash_id)

    result = query.run(as_dict=True)

    return result[0] if result else {"oot_count": 0}


from frappe.query_builder import DocType
from frappe.query_builder.functions import Count

# Распространённые причины выполнения заказа вне очереди (outOfTurnReason).
@frappe.whitelist()
def get_out_of_turn_reasons(start_date, end_date, car_wash_id=None):
    """
    Get out-of-turn reasons grouped by count using Frappe Query Builder.

    Args:
        start_date (str): Start date for filtering appointments
        end_date (str): End date for filtering appointments
        car_wash_id (str, optional): ID of specific car wash to filter by

    Returns:
        list: List of dictionaries with out_of_turn_reason and reason_count
    """
    appointment = DocType("Car wash appointment")

    query = (
        frappe.qb.from_(appointment)
        .select(
            appointment.out_of_turn_reason,
            Count("*").as_("reason_count")
        )
        .where(appointment.creation[start_date:end_date])
        .where(appointment.is_deleted == 0)
        .where(appointment.out_of_turn == 1)
        .where(appointment.out_of_turn_reason.isnotnull())
        .groupby(appointment.out_of_turn_reason)
        .orderby("reason_count", order=frappe.qb.desc)
    )

    # Conditional filtering by car_wash_id if provided
    if car_wash_id:
        query = query.where(appointment.car_wash == car_wash_id)

    return query.run(as_dict=True)

# Сравнение реальной длительности (workEndedOn - workStartedOn) с плановой (durationTotal). - ?
