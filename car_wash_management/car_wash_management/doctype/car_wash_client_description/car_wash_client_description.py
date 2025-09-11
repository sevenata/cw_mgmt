# Copyright (c) 2025, Rifat and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Carwashclientdescription(Document):
	def validate(self):
		# Ensure tags belong to the same car wash and no duplicates
		seen = set()
		for row in (self.get("tags") or []):
			if not row.tag:
				continue
			tag = frappe.db.get_value("Car wash tag", row.tag, ["name", "car_wash", "title"], as_dict=True)
			if not tag:
				frappe.throw("Invalid tag reference")
			if tag.car_wash != self.car_wash:
				frappe.throw(f"Tag {tag.title} belongs to another car wash")
			if tag.name in seen:
				frappe.throw(f"Duplicate tag {tag.title}")
			seen.add(tag.name)
