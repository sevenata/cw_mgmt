import frappe
from frappe.model.document import Document
from frappe.utils import today, now_datetime

from .booking_price_and_duration.booking import get_booking_price_and_duration
from .booking_price_and_duration.auto_discounts import record_auto_discount_usage, delete_recorded_auto_discount_usage
from .booking_price_and_duration.workflow_helpers import (
	compute_base_price_and_duration,
	get_disabled_auto_discount_ids_from_request_or_doc,
	set_auto_discount_usage_flags,
	refresh_usage,
	apply_usage,
)
from .availiability import update_cars_in_queue
from ...inventory import recalc_products_totals, reserve_products, unreserve_products

class Carwashbooking(Document):
    """Workflow:
    - validate: compute base totals without auto-discounts via helpers, refresh/apply
      recorded auto-discount usage, update totals and product rows, set payment ts,
      and update queue flags.
    - creation: record a snapshot of auto-discounts for current conditions.
    - on_update: on soft-delete unreserve products and delete recorded usage.
    - on_submit: reserve products.
    - on_cancel: unreserve products and delete recorded usage.
    Rationale: central helpers keep pricing/discount logic consistent across doctypes.
    """
    def before_insert(self):
        if not self.car_wash:
            frappe.throw(_("Car Wash is required"))

        max_num = frappe.db.sql(
            """
            SELECT MAX(CAST(num AS UNSIGNED)) FROM `tabCar wash appointment`
            WHERE DATE(creation) = %s AND car_wash = %s
            """,
            (today(), self.car_wash),
        )

        self.num = (max_num[0][0] or 0) + 1

        # Set confirmation statuses based on source_type
        if self.source_type in ["TelegramMiniApp", "TelegramBot"]:
            self.user_confirmation_status = "Pending"
            self.car_wash_confirmation_status = "Pending"
        else:
            self.user_confirmation_status = "Not applicable"
            self.car_wash_confirmation_status = "Not applicable"

    def validate(self):
        # Базовые суммы без применения автоскидок
        is_time_booking = bool(getattr(self, "is_time_booking", 0))
        base = compute_base_price_and_duration(
            self.car_wash,
            self.car,
            self.services,
            self.tariff,
            is_time_booking=is_time_booking,
            apply_auto_discounts=False,
        )

        # На создании зафиксируем usage с учетом отключений, если они переданы
        try:
            disabled_ids = get_disabled_auto_discount_ids_from_request_or_doc(self)
        except Exception:
            disabled_ids = set()

        try:
            if self.is_new() and not getattr(self, "is_deleted", 0):
                full = get_booking_price_and_duration(
                    self.car_wash,
                    self.car,
                    self.services,
                    self.tariff,
                    is_time_booking=is_time_booking,
                    user=getattr(self, "customer", None),
                )
                auto_result = (full.get("auto_discounts", {}) or {}).copy()
                applied_list = list(auto_result.get("applied_discounts", []) or [])
                if disabled_ids:
                    applied_list = [d for d in applied_list if d.get("discount_id") not in disabled_ids]
                filtered_auto_result = {
                    "applied_discounts": applied_list,
                    "total_service_discount": 0.0,
                    "commission_waived": 0.0,
                    "final_services_total": base.get("final_services_price", 0.0),
                    "final_commission": base.get("final_commission", 0.0),
                    "total_discount": 0.0,
                }
                record_auto_discount_usage(
                    self.car_wash,
                    getattr(self, "customer", None),
                    "Booking",
                    self.name,
                    filtered_auto_result,
                )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Record auto discount usage (booking) failed")

        # Если в документе есть список отключённых автоскидок, проставим флаги в usage
        try:
            if disabled_ids:
                set_auto_discount_usage_flags("Booking", self.name, disabled_ids)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Mark disabled auto discount usage failed")

        # Обновить usage под текущую базу
        refresh_usage(
            "Booking",
            self.name,
            base_services_total=base.get("final_services_price", 0.0),
            base_commission=base.get("final_commission", 0.0),
        )

        # Применим зафиксированные автоскидки (context: Booking)
        applied = apply_usage(
            context_type="Booking",
            context_id=self.name,
            base_services_total=base.get("final_services_price", 0.0),
            base_commission=base.get("final_commission", 0.0),
        )

        # Запишем поля документа
        self.services_total = applied["final_services_total"] + applied["final_commission"]
        self.duration_total = base["total_duration"]
        self.staff_reward_total = base["staff_reward_total"]

        # Пересчитать товары (если поле products есть)
        recalc_products_totals(self)

        if self.payment_status == "Paid" and self.payment_type and not self.payment_received_on:
            self.payment_received_on = now_datetime()

        # Handle has_appointment
        if self.appointment:
            self.has_appointment = True
        else:
            self.has_appointment = False

        update_cars_in_queue(self)

        # История применения автоскидок на создании уже записана выше

    def on_update(self):
        # Снятие резерва при soft-delete
        try:
            if self.has_value_changed("is_deleted") and getattr(self, "is_deleted", 0):
                unreserve_products(getattr(self, "products", []) or [])
                # Удалить записанные usage
                delete_recorded_auto_discount_usage("Booking", self.name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Booking on_update soft-delete unreserve failed")

    def on_submit(self):
        try:
            reserve_products(getattr(self, "products", []) or [])
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Booking on_submit reserve failed")

    def on_cancel(self):
        try:
            unreserve_products(getattr(self, "products", []) or [])
            delete_recorded_auto_discount_usage("Booking", self.name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Booking on_cancel unreserve failed")