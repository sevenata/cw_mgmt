# Copyright (c) 2024, Rifat and contributors
# For license information, please see license.txt

# import frappe
import uuid
from frappe.model.document import Document


class MobileAppUser(Document):
	def autoname(self):
            self.name = str(uuid.uuid4())
