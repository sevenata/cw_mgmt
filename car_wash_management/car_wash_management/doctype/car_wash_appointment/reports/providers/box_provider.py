# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/providers/box_provider.py
"""
Провайдер данных о боксах мойки.
"""

from typing import Any, Dict, List
import frappe
from .base_provider import DataProvider
from ..base import ReportContext


class BoxDataProvider(DataProvider):
    """Провайдер данных о боксах мойки"""
    
    def fetch_data(self, context: ReportContext) -> List[Dict[str, Any]]:
        """Загружает активные боксы мойки"""
        try:
            return frappe.get_all(
                "Car wash box",
                fields=["name", "type", "box_title"],
                filters={
                    "car_wash": context.car_wash,
                    "is_deleted": 0,
                    "is_disabled": 0,
                },
                order_by="name asc",
            )
        except Exception as e:
            frappe.log_error(f"Error fetching box data: {str(e)}", "BoxDataProvider")
            return []
