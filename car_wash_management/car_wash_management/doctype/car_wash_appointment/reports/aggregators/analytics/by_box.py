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
        # Построим мапу box_id -> title, если провайдер боксов уже загрузил названия
        box_title_by_id: Dict[str, str] = {}
        try:
            # Ленивая загрузка доступных боксов для текущей мойки
            rows = frappe.get_all(
                "Car wash box",
                fields=["name", "box_title"],
                filters={"car_wash": context.car_wash, "is_deleted": 0, "is_disabled": 0},
                limit=1000,
            )
            for r in rows:
                box_title_by_id[r["name"]] = r.get("box_title") or r["name"]
        except Exception:
            box_title_by_id = {}

        stat = defaultdict(lambda: {"visits": 0, "revenue": 0.0})
        for r in data:
            key = r.get("box") or "Unknown"
            stat[key]["visits"] += 1
            revenue_value = r.get("services_total")
            if revenue_value is None:
                revenue_value = r.get("grand_total")
            stat[key]["revenue"] += float(revenue_value or 0)

        result: List[Dict[str, Any]] = []
        for k, v in sorted(stat.items(), key=lambda kv: (-kv[1]["revenue"], kv[0])):
            result.append({
                "box": k,
                "box_title": box_title_by_id.get(k, k),
                "visits": v["visits"],
                "revenue": round(v["revenue"], 2),
            })
        return result
    
    def get_section_name(self) -> str:
        return "by_box"


