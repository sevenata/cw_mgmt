import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import IfNull

# Возвращает список работников и их роли.
@frappe.whitelist()
def get_workers_qb(car_wash_id=None):
    # Define the DocTypes
    worker = DocType('Car wash worker')
    user = DocType('User')

    # Build the query
    query = (
        frappe.qb.from_(worker)
        .left_join(user)
        .on(worker.user == user.name)
        .select(
            worker.name.as_('worker_id'),
            user.first_name,
            user.last_name,
            worker.role
        )
        .where(worker.is_deleted == 0)
        .where(worker.is_disabled == 0)
    )

    # Add company filter if provided
    if car_wash_id:
        query = query.where(worker.car_wash == car_wash_id)

    # Execute the query
    return query.run(as_dict=True)

from frappe.query_builder import DocType
from frappe.query_builder.functions import Count, Sum, Ifnull

# Возвращает список работников c показателями продуктивности - кол-во заказов и выручки.
@frappe.whitelist()
def get_worker_stats_sql(start_date, end_date, car_wash_id=None):
    """
    Get worker statistics using raw SQL approach.

    Args:
        start_date: Start date for filtering appointments
        end_date: End date for filtering appointments
        car_wash_id: Optional car wash ID to filter by

    Returns:
        List of dictionaries with worker stats
    """
    car_wash_condition = "AND a.car_wash = %(car_wash_id)s" if car_wash_id else ""

    sql_query = """
    SELECT
        w.name AS worker_id,
        COUNT(a.name) AS total_appointments,
        IFNULL(SUM(a.services_total), 0) AS total_revenue
    FROM
        `tabCar wash worker` AS w
    LEFT JOIN
        `tabCar wash appointment` AS a ON w.name = a.car_wash_worker
    WHERE
        a.creation BETWEEN %(start_date)s AND %(end_date)s
        AND a.is_deleted = 0
        {car_wash_condition}
    GROUP BY
        w.name
    """.format(car_wash_condition=car_wash_condition)

    params = {
        "start_date": start_date,
        "end_date": end_date,
        "car_wash_id": car_wash_id
    }

    return frappe.db.sql(sql_query, params, as_dict=True)

from frappe.query_builder import DocType
from frappe.query_builder.functions import Count

# Какие услуги чаще всего выполнял тот или иной сотрудник.
@frappe.whitelist()
def get_service_counts(start_date, end_date, worker_id=None):
    # Define the DocTypes
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
            Count("*").as_("service_count")
        )
        .where(
            (Appointment.creation.between(start_date, end_date)) &
            (Appointment.is_deleted == 0)
        )
        .groupby(Service.title)
        .orderby(Count("*"), order=frappe.qb.desc)
        .limit(20)
    )

    # Add conditional filter for worker_id if it's provided
    if worker_id:
        query = query.where(Appointment.car_wash_worker == worker_id)

    # Execute and return the results
    return query.run(as_dict=True)

import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import Count, Date

# Количество заказов на каждого работника по сменам/дням.
@frappe.whitelist()
def get_worker_appointments_by_day_sql(start_date, end_date, car_wash_id=None):
    """
    Get count of appointments per worker per day using raw SQL.

    Args:
        start_date (str): Start date in 'YYYY-MM-DD' format
        end_date (str): End date in 'YYYY-MM-DD' format
        car_wash_id (str, optional): Car wash ID to filter by

    Returns:
        List of dict with worker_id, day, and count_appointments
    """
    conditions = []
    params = {
        "start_date": start_date,
        "end_date": end_date
    }

    # Build the conditional part for car_wash_id
    car_wash_condition = ""
    if car_wash_id:
        car_wash_condition = "AND a.car_wash = %(car_wash_id)s"
        params["car_wash_id"] = car_wash_id

    # Construct and execute the SQL query
    sql_query = f"""
        SELECT w.name AS worker_id,
               DATE(a.starts_on) AS day,
               COUNT(a.name) AS count_appointments
        FROM `tabCar wash worker` AS w
        JOIN `tabCar wash appointment` AS a ON a.car_wash_worker = w.name
        WHERE a.starts_on BETWEEN %(start_date)s AND %(end_date)s
          AND a.is_deleted = 0
          {car_wash_condition}
        GROUP BY w.name, DATE(a.starts_on)
        ORDER BY day ASC
    """

    return frappe.db.sql(sql_query, params, as_dict=True)
