# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/analytics/by_day.py
"""
Агрегатор метрик по дням
"""

from collections import defaultdict
from typing import Any, Dict, List
import frappe
from ...base import MetricAggregator, ReportContext


class ByDayAggregator(MetricAggregator):
    """Агрегатор метрик по дням"""
    
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> Dict[str, Any]:
        """Агрегирует метрики по дням"""
        by_day = defaultdict(lambda: {"visits": 0, "revenue": 0.0})
        date_cache = {}
        
        for r in data:
            # Кэшируем парсинг даты
            starts_on_key = r["starts_on"]
            if starts_on_key not in date_cache:
                date_cache[starts_on_key] = frappe.utils.get_datetime(starts_on_key).date().isoformat()
            dkey = date_cache[starts_on_key]
            
            by_day[dkey]["visits"] += 1
            # Суммируем выручку по услугам; для обратной совместимости
            # используем grand_total, если services_total не задано
            revenue_value = r.get("services_total")
            if revenue_value is None:
                revenue_value = r.get("grand_total")
            by_day[dkey]["revenue"] += float(revenue_value or 0)
        
        return [
            {"date": d, "visits": v["visits"], "revenue": round(v["revenue"], 2)}
            for d, v in sorted(by_day.items(), key=lambda kv: kv[0])
        ]
    
    def get_section_name(self) -> str:
        return "by_day"
