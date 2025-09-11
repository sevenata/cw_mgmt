import frappe
from frappe.model.document import Document


class Carwashtag(Document):
	def validate(self):
		if not self.car_wash:
			frappe.throw("car_wash is required")
		if not self.title:
			frappe.throw("title is required")
		dup = frappe.db.sql(
			"""
			SELECT name FROM `tabCar wash tag`
			WHERE car_wash=%s AND LOWER(title)=LOWER(%s) AND name!=%s
			LIMIT 1
			""",
			(self.car_wash, self.title, self.name or ""),
		)
		if dup:
			frappe.throw("Tag with the same title already exists for this car wash")


