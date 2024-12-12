# Copyright (c) 2024, Rifat Dzhumagulov and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today, getdate
from datetime import datetime, timedelta

class Carwashservice(Document):
	pass

# http://localhost:8000/api/method/car_wash_management.car_wash_management.doctype.car_wash_service.car_wash_service.get_services_with_prices
# http://localhost:8000/api/method/car_wash_management.api.get_car_wash_services_with_prices
@frappe.whitelist(allow_guest=True)
def get_services_with_prices():
	return "123"

@frappe.whitelist(allow_guest=True)
def get_random():
	return "123"
