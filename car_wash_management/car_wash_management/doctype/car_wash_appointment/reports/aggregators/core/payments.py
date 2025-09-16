# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/core/payments.py
"""
Агрегатор метрик по платежам
"""

from collections import defaultdict
from typing import Any, Dict, List
from ...base import MetricAggregator, ReportContext


class PaymentsAggregator(MetricAggregator):
    """Агрегатор метрик по платежам"""
    
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> Dict[str, Any]:
        """Агрегирует метрики платежей"""
        payments_amount = defaultdict(float)
        payments_count = defaultdict(int)
        
        for r in data:
            if r.get("payment_status") == "Paid":
                ptype = r.get("payment_type") or "Unknown"
                amount = float(r.get("grand_total") or 0)
                payments_amount[ptype] += amount
                payments_count[ptype] += 1
        
        return {
            "breakdown": {
                k: {"amount": round(v, 2), "count": payments_count[k]}
                for k, v in sorted(payments_amount.items(), key=lambda kv: (-kv[1], kv[0]))
            }
        }
    
    def get_section_name(self) -> str:
        return "payments"
