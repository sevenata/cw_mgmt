# Copyright (c) 2024, Rifat and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import frappe

class Carwashserviceprice(Document):
	def on_update(self):
		cache = frappe.cache()
		# Сбросить ключи вида service_prices:tariff:{tariff_id}:*
		if self.doctype == "Car wash service price":
			cache.delete_keys(f"service_prices:tariff:{self.tariff}:")
		elif self.doctype == "Car wash tariff":
			cache.delete_keys(f"service_prices:tariff:{self.name}:")
