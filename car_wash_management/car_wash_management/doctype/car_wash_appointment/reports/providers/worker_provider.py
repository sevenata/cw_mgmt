# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/providers/worker_provider.py
"""
Провайдер данных о работниках.
"""

from typing import Any, Dict, List
import frappe
from .base_provider import DataProvider
from ..base import ReportContext


class WorkerDataProvider(DataProvider):
    """Провайдер данных о работниках"""
    
    def fetch_data(self, context: ReportContext) -> List[Dict[str, Any]]:
        """Загружает информацию о работниках"""
        return frappe.get_all(
            "Car wash worker",
            fields=["name", "full_name", "is_active"],
            filters={
                "is_active": 1,
            },
            order_by="full_name asc",
        )

