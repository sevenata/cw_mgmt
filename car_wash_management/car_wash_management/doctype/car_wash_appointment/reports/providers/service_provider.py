# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/providers/service_provider.py
"""
Провайдер данных об услугах.
"""

from typing import Any, Dict, List
import frappe
from .base_provider import DataProvider
from ..base import ReportContext


class ServiceDataProvider(DataProvider):
    """Провайдер данных об услугах"""
    
    def fetch_data(self, context: ReportContext) -> List[Dict[str, Any]]:
        """Загружает информацию об услугах"""
        return frappe.get_all(
            "Car wash service",
            fields=["name", "service_name", "price", "is_active"],
            filters={
                "is_active": 1,
            },
            order_by="service_name asc",
        )


