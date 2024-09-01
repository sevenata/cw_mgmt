# Copyright (c) 2024, Rifat Dzhumagulov and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import json
import frappe

class Carwashappointment(Document):
	pass
# 	@property
# 	def services_json(self):
# 		return frappe.utils.now_datetime() - self.creation

# 	def before_save(self):
#     		self.services_json = json.dumps(self.as_dict()['services'])
#     		self.save()
