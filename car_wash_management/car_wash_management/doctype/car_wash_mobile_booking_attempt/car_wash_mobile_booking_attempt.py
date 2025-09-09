# Copyright (c) 2025, Rifat and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ..car_wash_booking.booking_price_and_duration.auto_discounts import (
    get_applicable_auto_discounts_cached,
    apply_best_auto_discounts,
    record_auto_discount_usage,
    delete_recorded_auto_discount_usage,
)
from ..car_wash_booking.booking_price_and_duration.booking import get_booking_price_and_duration
from ..car_wash_booking.booking_price_and_duration.workflow_helpers import (
	compute_base_price_and_duration,
	get_disabled_auto_discount_ids_from_request_or_doc,
	set_auto_discount_usage_flags,
	refresh_usage,
	apply_usage,
)


class Carwashmobilebookingattempt(Document):
	"""Workflow:
	- validate: compute base totals via helpers (without auto-discounts), toggle disabled
	  usage, refresh/apply recorded usage; write final `services_total`, `commission_user`,
	  and `total`.
	- after_insert: determine best applicable auto-discounts and record usage snapshot.
	- on_trash: delete recorded usage for this attempt.
	Rationale: aligns mobile attempt calculations and toggles with booking/appointment via helpers.
	"""
	
	def has_shop_feature(self):
		"""
		Check if the car wash has the shop feature enabled
		Results are cached for 3 minutes to improve performance
		
		Returns:
			bool: True if shop feature is available, False otherwise
		"""
		if not self.car_wash:
			return False
			
		car_wash_doc = frappe.get_doc("Car wash", self.car_wash)
		return car_wash_doc.has_journal_feature("shop")
	def validate(self):
		# База без автоскидок, затем применим зафиксированные usage (context: MobileAttempt)
		base = compute_base_price_and_duration(
			self.car_wash,
			self.car,
			getattr(self, "services", []) or [],
			getattr(self, "tariff", None),
			is_time_booking=bool(getattr(self, "is_time_booking", 0)),
			created_by_admin=False,
			apply_auto_discounts=False,
		)

		# Проставить/снять флаги отключённых скидок в usage, если список передан через форму
		try:
			disabled_ids = get_disabled_auto_discount_ids_from_request_or_doc(self)
			if disabled_ids:
				# for MobileAttempt we align with appointment behavior: enable others too
				set_auto_discount_usage_flags("MobileAttempt", self.name, disabled_ids, enable_others=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Mark disabled auto discount usage (mobile attempt) failed")

		# Обновить usage под текущую базу
		refresh_usage(
			"MobileAttempt",
			self.name,
			base_services_total=base.get("final_services_price", 0.0),
			base_commission=base.get("final_commission", 0.0),
		)

		applied = apply_usage(
			context_type="MobileAttempt",
			context_id=self.name,
			base_services_total=base.get("final_services_price", 0.0),
			base_commission=base.get("final_commission", 0.0),
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
			
			# Проверяем наличие фичи promo у мойки
			car_wash_doc = frappe.get_doc("Car wash", self.car_wash)
			has_promo_feature = car_wash_doc.has_journal_feature("promo")
			if not has_promo_feature:
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
