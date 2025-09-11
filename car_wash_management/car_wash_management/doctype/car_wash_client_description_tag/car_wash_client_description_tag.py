import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class Carwashclientdescriptiontag(Document):
	def before_insert(self):
		self.assigned_by = frappe.session.user
		self.assigned_on = now_datetime()


