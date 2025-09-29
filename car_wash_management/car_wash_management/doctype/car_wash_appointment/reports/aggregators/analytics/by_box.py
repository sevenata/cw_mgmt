# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/analytics/by_box.py
"""
Агрегатор метрик по боксам
"""

from collections import defaultdict
from typing import Any, Dict, List
from ...base import MetricAggregator, ReportContext


class ByBoxAggregator(MetricAggregator):
    """Разрез по боксам"""
    
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> List[Dict[str, Any]]:
        stat = defaultdict(lambda: {"visits": 0, "revenue": 0.0})
        for r in data:
            key = r.get("box") or "Unknown"
            stat[key]["visits"] += 1
            revenue_value = r.get("services_total")
            if revenue_value is None:
                revenue_value = r.get("grand_total")
            stat[key]["revenue"] += float(revenue_value or 0)
        return [
            {"box": k, "visits": v["visits"], "revenue": round(v["revenue"], 2)}
            for k, v in sorted(stat.items(), key=lambda kv: (-kv[1]["revenue"], kv[0]))
        ]
    
    def get_section_name(self) -> str:
        return "by_box"


