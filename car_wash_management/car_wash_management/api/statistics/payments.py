import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import Count, IfNull, Sum, Avg
from frappe.query_builder import DocType, functions as fn

# Выручка, разбитая по способам оплаты (PaymentType).
@frappe.whitelist()
def get_payment_type_totals_sql(start_date, end_date, car_wash_id=None):
    """
    Get total amount grouped by payment type using direct SQL.

    Args:
        start_date (str): Start date for filtering appointments
        end_date (str): End date for filtering appointments
        car_wash_id (str, optional): Car wash ID to filter by

    Returns:
        list: List of dictionaries with payment_type and total_amount
    """
    conditions = []
    values = {
        "start_date": start_date,
        "end_date": end_date
    }

    # Build the WHERE conditions
    conditions.append("a.creation BETWEEN %(start_date)s AND %(end_date)s")
    conditions.append("a.is_deleted = 0")
    conditions.append("a.payment_type IS NOT NULL")
    conditions.append("a.payment_type != 'Mixed'")

    if car_wash_id:
        conditions.append("a.car_wash = %(car_wash_id)s")
        values["car_wash_id"] = car_wash_id

    where_clause = " AND ".join(conditions)

    # Execute the SQL query
    query = f"""
        SELECT a.payment_type, SUM(IFNULL(a.services_total, 0)) AS total_amount
        FROM `tabCar wash appointment` AS a
        WHERE {where_clause}
        GROUP BY a.payment_type
    """

    return frappe.db.sql(query, values=values, as_dict=1)


from frappe.query_builder import DocType
from frappe.query_builder.functions import Sum

@frappe.whitelist()
def get_custom_payment_methods_summary(start_date, end_date, car_wash_id=None):
    """
    Get summary of custom payment methods between specified dates.

    Args:
        start_date (str): Start date in YYYY-MM-DD format
        end_date (str): End date in YYYY-MM-DD format
        car_wash_id (str, optional): Car wash ID to filter by

    Returns:
        list: List of dictionaries with custom_method and total_amount
    """
    # Define DocType objects for each table
    MixedPayment = DocType("Car wash mixed payment")
    Appointment = DocType("Car wash appointment")
    CustomPaymentMethod = DocType("Car wash custom payment method")

    # Build the query using frappe.qb
    query = (
        frappe.qb.from_(MixedPayment)
        .join(Appointment).on(MixedPayment.parent == Appointment.name)
        .join(CustomPaymentMethod).on(MixedPayment.custom_payment_method == CustomPaymentMethod.name)
        .select(
            CustomPaymentMethod.title.as_("custom_method"),
            Sum(MixedPayment.amount).as_("total_amount")
        )
        .where(
            (Appointment.creation.between(start_date, end_date)) &
            (Appointment.is_deleted == 0) &
            (MixedPayment.payment_type == "Custom")
        )
        .groupby(CustomPaymentMethod.title)
        .orderby(Sum(MixedPayment.amount).as_("total_amount"), order=frappe.qb.desc)
    )

    # Add car_wash filter if provided
    if car_wash_id:
        query = query.where(Appointment.car_wash == car_wash_id)

    # Execute the query and return results
    return query.run(as_dict=True)

# Как часто встречаются смешанные оплаты (Mixed) и на какую сумму.
@frappe.whitelist()
def get_mixed_payment_stats_raw_sql(start_date, end_date, car_wash_id=None):
    filters = {
        "start_date": start_date,
        "end_date": end_date,
        "car_wash_id": car_wash_id
    }

    # Note: In Frappe, child table records are stored with 'parent' field
    # instead of 'appointment' as in the original SQL
    query = """
    SELECT COUNT(DISTINCT a.name) AS mixed_count,
           IFNULL(SUM(mp.amount), 0) AS total_mixed_amount
      FROM `tabCar wash appointment` AS a
      JOIN `tabCar wash mixed payment` AS mp ON a.name = mp.parent
     WHERE a.creation BETWEEN %(start_date)s AND %(end_date)s
       AND a.is_deleted = 0
       AND a.payment_type = 'Mixed'
    """

    if car_wash_id:
        query += " AND a.car_wash = %(car_wash_id)s"

    result = frappe.db.sql(query, filters, as_dict=True)
    return result[0] if result else {"mixed_count": 0, "total_mixed_amount": 0}

# Средний чек в разрезе способов оплаты.
@frappe.whitelist()
def get_payment_type_avg_check(start_date=None, end_date=None, car_wash_id=None):
    """
    Get average check value grouped by payment type

    Args:
        start_date: Start date for filtering
        end_date: End date for filtering
        car_wash_id: Optional car wash filter

    Returns:
        List of dictionaries with payment_type and avg_check
    """
    # Define the DocType reference
    appointment = DocType("Car wash appointment")

    # Build the query
    query = (
        frappe.qb.from_(appointment)
        .select(
            appointment.payment_type,
            IfNull(Avg(appointment.services_total), 0).as_("avg_check")
        )
        .where(
            (appointment.creation.between(start_date, end_date)) &
            (appointment.is_deleted == 0) &
            (appointment.payment_type.isnotnull())
        )
        .groupby(
            appointment.payment_type
        )
    )

    # Add optional car_wash filter if provided
    if car_wash_id:
        query = query.where(appointment.car_wash == car_wash_id)

    # Execute the query and return results
    return query.run(as_dict=True)
