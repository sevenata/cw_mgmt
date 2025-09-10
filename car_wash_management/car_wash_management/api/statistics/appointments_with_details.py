import frappe
from frappe.query_builder import DocType
from frappe.utils import getdate, add_days


@frappe.whitelist()
def get_appointments_with_details(
    car_wash=None,
    boxes=None,
    workers=None,
    services=None,
    statuses=None,
    payment_status=None,
    customers=None,
    starts_on=None,
    end_date=None,
    limit=200,
    is_deleted=0
):
    """
    Get appointments with detailed service information in a single query.
    This method optimizes the data fetching by including service details
    directly in the main query instead of making separate API calls.
    
    Args:
        car_wash (str): Car wash ID to filter by
        boxes (list): List of box IDs to filter by
        workers (list): List of worker names to filter by
        services (list): List of service IDs to filter by
        statuses (list): List of workflow states to filter by
        payment_status (str): Payment status filter
        customers (list): List of customer IDs to filter by
        starts_on (str): Start date in YYYY-MM-DD format
        end_date (str): End date in YYYY-MM-DD format
        limit (int): Maximum number of records to return
        is_deleted (int): Filter by deletion status (0 or 1)
    
    Returns:
        list: List of appointment dictionaries with embedded service details
    """
    
    # Normalize list inputs (None/empty to [])
    boxes = boxes or []
    workers = workers or []
    services = services or []
    statuses = statuses or []
    customers = customers or []

    # Main doctypes
    appointment = DocType("Car wash appointment")
    service = DocType("Car wash appointment service")

    # Build filterable base for appointments only
    base = frappe.qb.from_(appointment).select(appointment.name)

    if car_wash:
        base = base.where(appointment.car_wash == car_wash)

    # is_deleted filter: if None, exclude deleted; else exact match
    if is_deleted is not None:
        base = base.where(appointment.is_deleted == is_deleted)
    else:
        base = base.where(appointment.is_deleted != 1)

    if payment_status:
        base = base.where(appointment.payment_status == payment_status)

    # Date filters: supports starts_on only (same-day window) or explicit end_date (inclusive of start, exclusive of next day after end)
    if starts_on and not end_date:
        start_date = getdate(starts_on)
        next_day = add_days(start_date, 1)
        base = base.where(appointment.starts_on >= start_date).where(appointment.starts_on < next_day)
    elif starts_on and end_date:
        start_date = getdate(starts_on)
        end_date_dt = getdate(end_date)
        next_day_after_end = add_days(end_date_dt, 1)
        base = base.where(appointment.starts_on >= start_date).where(appointment.starts_on < next_day_after_end)

    if boxes:
        base = base.where(appointment.box.isin(boxes))

    if workers:
        base = base.where(appointment.car_wash_worker.isin(workers))

    if statuses:
        base = base.where(appointment.workflow_state.isin(statuses))

    if customers:
        base = base.where(appointment.customer.isin(customers))

    # If filtering by services, we need to join service to the base, but only to constrain the set of appointment names. We'll compute names via a distinct select.
    if services:
        svc = frappe.qb.from_(service).select(service.parent).where(service.service.isin(services))
        base = base.where(appointment.name.isin(svc))

    # Order and limit at the appointment level to ensure correct limit semantics (distinct appointments)
    base = base.orderby(appointment.creation, order=frappe.qb.desc)
    if limit:
        base = base.limit(limit)

    # Use the appointment-name subquery as a source for joining details
    base_alias = base.as_("base")

    query = (
        frappe.qb.from_(base_alias)
        .join(appointment)
        .on(appointment.name == base_alias.name)
        .left_join(service)
        .on(appointment.name == service.parent)
        .select(
            appointment.name,
            appointment.num,
            appointment.box,
            appointment.box_title,
            appointment.box_color,
            appointment.workflow_state,
            appointment.starts_on,
            appointment.work_started_on,
            appointment.work_ended_on,
            appointment.ends_on,
            appointment.car_wash_worker,
            appointment.car_wash_worker_name,
            appointment.services_total,
            appointment.duration_total,
            appointment.customer,
            appointment.car,
            appointment.car_color,
            appointment.car_model,
            appointment.car_model_name,
            appointment.car_make,
            appointment.car_make_name,
            appointment.car_license_plate,
            appointment.car_body_type,
            appointment.payment_type,
            appointment.payment_status,
            appointment.payment_received_on,
            appointment.is_deleted,
            appointment.out_of_turn,
            appointment.out_of_turn_reason,
            appointment.tariff,
            service.name.as_("service_name"),
            service.service,
            service.service_name.as_("service_title"),
            service.color.as_("service_color"),
            service.price,
            service.duration,
            service.staff_reward,
        )
    )

    results = query.run(as_dict=True)
    
    # Group services by appointment
    appointments_dict = {}
    
    for row in results:
        appointment_id = row.name
        
        if appointment_id not in appointments_dict:
            # Create appointment entry
            appointment_data = {
                "name": row.name,
                "num": row.num,
                "box": row.box,
                "box_title": row.box_title,
                "box_color": row.box_color,
                "workflow_state": row.workflow_state,
                "starts_on": row.starts_on,
                "work_started_on": row.work_started_on,
                "work_ended_on": row.work_ended_on,
                "ends_on": row.ends_on,
                "car_wash_worker": row.car_wash_worker,
                "car_wash_worker_name": row.car_wash_worker_name,
                "services_total": row.services_total,
                "duration_total": row.duration_total,
                "customer": row.customer,
                "car": row.car,
                "car_color": row.car_color,
                "car_model": row.car_model,
                "car_model_name": row.car_model_name,
                "car_make": row.car_make,
                "car_make_name": row.car_make_name,
                "car_license_plate": row.car_license_plate,
                "car_body_type": row.car_body_type,
                "payment_type": row.payment_type,
                "payment_status": row.payment_status,
                "payment_received_on": row.payment_received_on,
                "is_deleted": row.is_deleted,
                "out_of_turn": row.out_of_turn,
                "out_of_turn_reason": row.out_of_turn_reason,
                "tariff": row.tariff,
                "services": []
            }
            appointments_dict[appointment_id] = appointment_data
        
        # Add service if it exists
        if row.service_name:
            service_data = {
                "name": row.service_name,
                "service": row.service,
                "service_name": row.service_title,
                "color": row.service_color,
                "price": row.price,
                "duration": row.duration,
                "staff_reward": row.staff_reward
            }
            appointments_dict[appointment_id]["services"].append(service_data)
    
    # Convert to list
    appointments_list = list(appointments_dict.values())
    
    return appointments_list


@frappe.whitelist()
def get_appointments_with_details_by_date_range(
    start_date,
    end_date,
    car_wash=None,
    boxes=None,
    workers=None,
    services=None,
    statuses=None,
    payment_status=None,
    customers=None,
    limit=200,
    is_deleted=0
):
    """
    Get appointments with details for a specific date range.
    This is a convenience wrapper around get_appointments_with_details.
    """
    return get_appointments_with_details(
        car_wash=car_wash,
        boxes=boxes,
        workers=workers,
        services=services,
        statuses=statuses,
        payment_status=payment_status,
        customers=customers,
        starts_on=start_date,
        end_date=end_date,
        limit=limit,
        is_deleted=is_deleted
    )