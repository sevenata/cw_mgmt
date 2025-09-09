# Copyright (c) 2025, Rifat and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ..car_wash_booking.booking_price_and_duration.auto_discounts import (
    get_applicable_auto_discounts_cached,
    apply_best_auto_discounts,
    record_auto_discount_usage,
    apply_recorded_auto_discounts_to_base,
    delete_recorded_auto_discount_usage,
    refresh_recorded_auto_discount_usage,
)
from ..car_wash_booking.booking_price_and_duration.booking import get_booking_price_and_duration


class Carwashmobilebookingattempt(Document):
	def validate(self):
		# База без автоскидок, затем применим зафиксированные usage (context: MobileAttempt)
		base = get_booking_price_and_duration(
			self.car_wash,
			self.car,
			getattr(self, "services", []) or [],
			getattr(self, "tariff", None),
			is_time_booking=bool(getattr(self, "is_time_booking", 0)),
			created_by_admin=False,
			apply_auto_discounts=False,
		)

		# Обновить usage под текущую базу
		refresh_recorded_auto_discount_usage(
			"MobileAttempt",
			self.name,
			base_services_total=base.get("final_services_price", 0.0),
			base_commission=base.get("final_commission", 0.0),
		)

		applied = apply_recorded_auto_discounts_to_base(
			base_services_total=base.get("final_services_price", 0.0),
			base_commission=base.get("final_commission", 0.0),
			context_type="MobileAttempt",
			context_id=self.name,
		)
		# total хранится как services_total + commission_user
		self.services_total = applied["final_services_total"]
		self.commission_user = applied["final_commission"]
		self.total = applied["final_services_total"] + applied["final_commission"]

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

	def on_trash(self):
		try:
			delete_recorded_auto_discount_usage("MobileAttempt", self.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Mobile attempt delete usage failed")
