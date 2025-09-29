"""Сегментация автопарка: марка/модель"""

from collections import defaultdict
from typing import Any, Dict, List
from ...base import MetricAggregator, ReportContext


class CarSegmentAggregator(MetricAggregator):
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> Dict[str, Any]:
        by_make = defaultdict(lambda: {"visits": 0, "revenue": 0.0})
        by_model = defaultdict(lambda: {"visits": 0, "revenue": 0.0})
        for r in data:
            make = r.get("car_make") or "Unknown"
            model = r.get("car_model") or "Unknown"
            by_make[make]["visits"] += 1
            revenue_value = r.get("services_total")
            if revenue_value is None:
                revenue_value = r.get("grand_total")
            by_make[make]["revenue"] += float(revenue_value or 0)
            by_model[model]["visits"] += 1
            revenue_value_model = r.get("services_total")
            if revenue_value_model is None:
                revenue_value_model = r.get("grand_total")
            by_model[model]["revenue"] += float(revenue_value_model or 0)
        return {
            "make": [
                {"key": k, "visits": v["visits"], "revenue": round(v["revenue"], 2)}
                for k, v in sorted(by_make.items(), key=lambda kv: (-kv[1]["revenue"], kv[0]))[:20]
            ],
            "model": [
                {"key": k, "visits": v["visits"], "revenue": round(v["revenue"], 2)}
                for k, v in sorted(by_model.items(), key=lambda kv: (-kv[1]["revenue"], kv[0]))[:20]
            ],
        }

    def get_section_name(self) -> str:
        return "car_segment"


