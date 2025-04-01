# OPTION 1: Using frappe.qb - Most direct translation of the SQL query
import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import Count

# В какие бокс чаще всего записываются за указанный период.
@frappe.whitelist()
def get_most_used_boxes(start_date, end_date, car_wash_id=None):
    """
    Get the most frequently used box within a date range, optionally filtered by car wash.

    Args:
        start_date (str): Start date for the query
        end_date (str): End date for the query
        car_wash_id (str, optional): Car wash ID to filter by

    Returns:
        dict: Box title and appointment count
    """
    # Define the DocTypes we'll be working with
    appointment = DocType("Car wash appointment")
    box = DocType("Car wash box")

    # Build the query using frappe.qb
    query = (
        frappe.qb.from_(appointment)
        .join(box).on(appointment.box == box.name)
        .select(
            box.box_title.as_("box_title"),
            Count(appointment.name).as_("total_appointments")
        )
        .where(
            (appointment.starts_on[start_date:end_date]) &
            (appointment.is_deleted == 0)
        )
        .groupby(box.box_title)
        .orderby(Count(appointment.name), order=frappe.qb.desc)
        .limit(10)
    )

    # Add car_wash filter if provided
    if car_wash_id:
        query = query.where(box.car_wash == car_wash_id)

    # Execute the query and return result
    result = query.run(as_dict=True)
    return result

# Сколько боксов одновременно занято в пиковые часы.
@frappe.whitelist()
def get_hourly_box_usage(start_date, end_date, car_wash_id=None):
    conditions = ["a.is_deleted = 0",
                 "a.starts_on BETWEEN %(start_date)s AND %(end_date)s"]

    if car_wash_id:
        conditions.append("a.car_wash = %(car_wash_id)s")

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT HOUR(a.starts_on) AS hour_slot,
               COUNT(DISTINCT a.box) AS boxes_in_use
        FROM `tabCar wash appointment` AS a
        WHERE {where_clause}
        GROUP BY HOUR(a.starts_on)
        ORDER BY boxes_in_use DESC
    """

    values = {
        "start_date": start_date,
        "end_date": end_date,
        "car_wash_id": car_wash_id
    }

    return frappe.db.sql(query, values=values, as_dict=True)
