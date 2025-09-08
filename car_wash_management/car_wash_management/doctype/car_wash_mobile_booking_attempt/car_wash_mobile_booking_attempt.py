# Copyright (c) 2025, Rifat and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ..car_wash_booking.booking_price_and_duration.auto_discounts import (
    get_applicable_auto_discounts_cached,
    apply_best_auto_discounts,
    record_auto_discount_usage,
)


class Carwashmobilebookingattempt(Document):
	def after_insert(self):
		# Запишем историю автоскидок на момент создания попытки бронирования
		try:
			if getattr(self, "is_deleted", 0):
				return
			applicable = get_applicable_auto_discounts_cached(
				car_wash=self.car_wash,
				customer=getattr(self, "user", None),
				services=getattr(self, "services", []) or [],
				services_total=float(getattr(self, "services_total", 0.0) or 0.0),
				cache_ttl_sec=60,
			)
			best = apply_best_auto_discounts(
				applicable_discounts=applicable,
				services_total=float(getattr(self, "services_total", 0.0) or 0.0),
				commission_amount=float(getattr(self, "commission_user", 0.0) or 0.0),
				allow_combinations=True,
			)
			record_auto_discount_usage(
				self.car_wash,
				getattr(self, "user", None),
				"MobileAttempt",
				self.name,
				best,
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Record auto discount usage (mobile attempt) failed")
