# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/special/payment_lag.py
"""
Агрегатор метрик по лагу оплаты
"""

from typing import Any, Dict, List
import frappe
from ...base import MetricAggregator, ReportContext


class PaymentLagAggregator(MetricAggregator):
    """Лаг оплаты относительно завершения работы"""
    
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> Dict[str, Any]:
        count = 0
        total_minutes = 0.0
        max_minutes = 0.0
        for r in data:
            if (r.get("payment_status") == "Paid") and r.get("payment_received_on") and r.get("work_ended_on"):
                delta_min = (frappe.utils.get_datetime(r["payment_received_on"]) - frappe.utils.get_datetime(r["work_ended_on"]))\
                    .total_seconds() / 60.0
                count += 1
                total_minutes += max(0.0, delta_min)
                max_minutes = max(max_minutes, delta_min)
        return {
            "avg_minutes": round((total_minutes / count) if count else 0.0, 2),
            "max_minutes": round(max_minutes, 2),
            "samples": count,
        }
    
    def get_section_name(self) -> str:
        return "payment_lag"
