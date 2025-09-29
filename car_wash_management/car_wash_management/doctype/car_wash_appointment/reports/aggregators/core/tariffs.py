"""Эффективность тарифов"""

from collections import defaultdict
from typing import Any, Dict, List
import frappe
from ...base import MetricAggregator, ReportContext


class TariffsAggregator(MetricAggregator):
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> List[Dict[str, Any]]:
        by_tariff = defaultdict(lambda: {"count": 0, "revenue": 0.0})
        for r in data:
            key = r.get("tariff") or "Unknown"
            by_tariff[key]["count"] += 1
            revenue_value = r.get("services_total")
            if revenue_value is None:
                revenue_value = r.get("grand_total")
            by_tariff[key]["revenue"] += float(revenue_value or 0)
        # Загрузим названия тарифов для текущей мойки
        tariff_title_by_id: Dict[str, str] = {}
        try:
            rows = frappe.get_all(
                "Car wash tariff",
                fields=["name", "tariff_name"],
                filters={"car_wash": context.car_wash, "is_active": 1, "is_deleted": 0},
                limit=2000,
            )
            for r in rows:
                tariff_title_by_id[r["name"]] = r.get("tariff_name") or r["name"]
        except Exception:
            tariff_title_by_id = {}

        res = []
        total_visits = sum(v["count"] for v in by_tariff.values()) or 1
        for k, v in by_tariff.items():
            avg_check = (v["revenue"] / v["count"]) if v["count"] else 0.0
            res.append({
                "tariff": k,
                "tariff_title": tariff_title_by_id.get(k, k),
                "visits": v["count"],
                "revenue": round(v["revenue"], 2),
                "avg_check": round(avg_check, 2),
                "share_pct": round(v["count"] / total_visits * 100.0, 2),
            })
        return sorted(res, key=lambda x: (-x["revenue"], -x["visits"]))

    def get_section_name(self) -> str:
        return "tariffs"


