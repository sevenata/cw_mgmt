# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/providers/appointment_provider.py
"""
Провайдер данных о записях на мойку.
"""

from typing import Any, Dict, List
import frappe
from .base_provider import DataProvider
from ..base import ReportContext


class AppointmentDataProvider(DataProvider):
    """Провайдер данных о записях на мойку"""
    
    def __init__(self, fields: List[str] = None):
        self.fields = fields or [
            "name",
            "starts_on",
            "ends_on", 
            "work_started_on",
            "work_ended_on",
            "payment_status",
            "payment_type",
            "payment_received_on",
            "services_total",
            "products_total",
            "grand_total",
            "box",
            "car_wash_worker",
            "car_wash_worker_name",
            "staff_reward_total",
            "out_of_turn",
            "cancellation_reason",
            "customer",
            "tariff",
            "car_make",
            "car_model",
        ]
    
    def fetch_data(self, context: ReportContext) -> List[Dict[str, Any]]:
        """Загружает записи за обе недели одним запросом"""
        try:
            return frappe.get_all(
                "Car wash appointment",
                fields=self.fields,
                filters={
                    "car_wash": context.car_wash,
                    "is_deleted": 0,
                    "starts_on": ["between", [context.previous_week.start, context.current_week.end]],
                },
                order_by="starts_on asc",
                limit=10000,  # Защита от перегрузки при больших объемах данных
            )
        except Exception as e:
            frappe.log_error(f"Error fetching appointment data: {str(e)}", "AppointmentDataProvider")
            return []
    
    def fetch_current_week_data(self, context: ReportContext) -> List[Dict[str, Any]]:
        """Загружает записи только за текущую неделю"""
        try:
            return frappe.get_all(
                "Car wash appointment",
                fields=self.fields,
                filters={
                    "car_wash": context.car_wash,
                    "is_deleted": 0,
                    "starts_on": ["between", [context.current_week.start, context.current_week.end]],
                },
                order_by="starts_on asc",
                limit=5000,  # Лимит для одной недели
            )
        except Exception as e:
            frappe.log_error(f"Error fetching current week data: {str(e)}", "AppointmentDataProvider")
            return []
