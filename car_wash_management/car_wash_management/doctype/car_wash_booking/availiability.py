import frappe


def create_availability(doc):
    boxes_count = frappe.db.count('Car wash box', {'car_wash': doc.car_wash})
    cars_in_queue = get_cars_in_queue(doc)
    availability_doc = frappe.get_doc({
        "doctype": "Car wash availability",
        "name": doc.car_wash,
        "car_wash": doc.car_wash,
        "boxes_count": boxes_count,
        "cars_in_boxes": 0,
        "cars_in_queue": cars_in_queue,
        "is_working_now": 1
    })
    availability_doc.insert(ignore_permissions=True)


def update_or_create_availability(doc):
    try:
        update_queue_num(doc)
    except frappe.DoesNotExistError:
        create_availability(doc)
        return


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
    return frappe.db.count("Car wash booking", {"has_appointment": False,"is_cancelled":False,"is_deleted":False,"car_wash": doc.car_wash})


def update_queue_num(doc):
    availability_doc = frappe.get_doc("Car wash availability", doc.car_wash)
    boxes_count = frappe.db.count('Car wash box', {'car_wash': doc.car_wash})
    availability_doc.cars_in_queue = get_cars_in_queue(doc)
    availability_doc.boxes_count = boxes_count
    availability_doc.save(ignore_permissions=True)
