# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/core/revenue.py
"""
Агрегатор метрик по выручке
"""

from typing import Any, Dict, List
from ...base import MetricAggregator, ReportContext


class RevenueAggregator(MetricAggregator):
    """Агрегатор метрик по выручке"""
    
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> Dict[str, Any]:
        """Агрегирует метрики выручки"""
        total = 0.0
        services_total = 0.0
        products_total = 0.0
        paid_count = 0
        
        for r in data:
            gt = float(r.get("grand_total") or 0)
            st = float(r.get("services_total") or 0)
            pt = float(r.get("products_total") or 0)
            
            total += gt
            services_total += st
            products_total += pt
            
            if r.get("payment_status") == "Paid":
                paid_count += 1
        
        avg_check = (total / paid_count) if paid_count > 0 else 0.0
        
        return {
            "grand_total": round(total, 2),
            "services_total": round(services_total, 2),
            "products_total": round(products_total, 2),
            "avg_check": round(avg_check, 2),
        }
    
    def get_section_name(self) -> str:
        return "revenue"
