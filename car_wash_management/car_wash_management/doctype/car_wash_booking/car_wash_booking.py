# Copyright (c) 2024, Rifat and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class Carwashbooking(Document):
    def before_insert(self):
        if not self.car_wash:
            frappe.throw("Car Wash is required")

        max_num = frappe.db.sql(
            """
            SELECT CAST(MAX(num) AS SIGNED) FROM `tabCar wash booking`
            WHERE DATE(creation) = %s AND car_wash = %s
            """,
            (today(), self.car_wash),
        )

        self.num = (max_num[0][0] or 0) + 1
