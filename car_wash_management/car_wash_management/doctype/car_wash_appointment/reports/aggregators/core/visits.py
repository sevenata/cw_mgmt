# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/core/visits.py
"""
Агрегатор метрик по посещениям
"""

from typing import Any, Dict, List
from ...base import MetricAggregator, ReportContext


class VisitsAggregator(MetricAggregator):
    """Агрегатор метрик по посещениям"""
    
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> Dict[str, Any]:
        """Агрегирует метрики посещений"""
        total = len(data)
        paid = sum(1 for r in data if r.get("payment_status") == "Paid")
        unpaid = total - paid
        
        return {
            "total": total,
            "paid": paid,
            "unpaid": unpaid,
        }
    
    def get_section_name(self) -> str:
        return "visits"

