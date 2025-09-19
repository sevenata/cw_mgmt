# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/providers/payment_provider.py
"""
Провайдер данных о платежах.
"""

from typing import Any, Dict, List
import frappe
from .base_provider import DataProvider
from ..base import ReportContext


class PaymentDataProvider(DataProvider):
    """Провайдер данных о платежах"""
    
    def fetch_data(self, context: ReportContext) -> List[Dict[str, Any]]:
        """Загружает детальную информацию о платежах"""
        return frappe.get_all(
            "Payment Entry",
            fields=[
                "name",
                "posting_date",
                "paid_amount",
                "payment_type",
                "mode_of_payment",
                "reference_no",
            ],
            filters={
                "docstatus": 1,
                "posting_date": ["between", [context.previous_week.start, context.current_week.end]],
            },
            order_by="posting_date asc",
        )

