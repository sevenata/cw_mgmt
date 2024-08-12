# Copyright (c) 2024, Rifat and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
from frappe.utils import now


class WorkShiftSchedule(Document):
	def on_update(self):
		if self.workflow_state == 'Closed':
			self.end_time = now()
