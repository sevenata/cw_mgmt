"""Эффективность тарифов"""

from collections import defaultdict
from typing import Any, Dict, List
from ...base import MetricAggregator, ReportContext


class TariffsAggregator(MetricAggregator):
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> List[Dict[str, Any]]:
        by_tariff = defaultdict(lambda: {"count": 0, "revenue": 0.0})
        for r in data:
            key = r.get("tariff") or "Unknown"
            by_tariff[key]["count"] += 1
            by_tariff[key]["revenue"] += float(r.get("grand_total") or 0)
        res = []
        total_visits = sum(v["count"] for v in by_tariff.values()) or 1
        for k, v in by_tariff.items():
            avg_check = (v["revenue"] / v["count"]) if v["count"] else 0.0
            res.append({
                "tariff": k,
                "visits": v["count"],
                "revenue": round(v["revenue"], 2),
                "avg_check": round(avg_check, 2),
                "share_pct": round(v["count"] / total_visits * 100.0, 2),
            })
        return sorted(res, key=lambda x: (-x["revenue"], -x["visits"]))

    def get_section_name(self) -> str:
        return "tariffs"


