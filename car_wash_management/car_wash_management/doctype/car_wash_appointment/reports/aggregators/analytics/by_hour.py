# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/analytics/by_hour.py
"""
Агрегатор метрик по часам
"""

from collections import defaultdict
from typing import Any, Dict, List
import frappe
from ...base import MetricAggregator, ReportContext


class ByHourAggregator(MetricAggregator):
    """Разрез по часам"""
    
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> List[Dict[str, Any]]:
        buckets = defaultdict(lambda: {"visits": 0, "revenue": 0.0})
        for r in data:
            ts = r.get("starts_on")
            if not ts:
                continue
            dt = frappe.utils.get_datetime(ts)
            hour_key = f"{dt.hour:02d}:00"
            buckets[hour_key]["visits"] += 1
            buckets[hour_key]["revenue"] += float(r.get("grand_total") or 0)
        return [
            {"hour": k, "visits": v["visits"], "revenue": round(v["revenue"], 2)}
            for k, v in sorted(buckets.items(), key=lambda kv: kv[0])
        ]
    
    def get_section_name(self) -> str:
        return "by_hour"
