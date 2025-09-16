# services portfolio aggregator

from typing import Any, Dict, List
import frappe
from ...base import MetricAggregator, ReportContext


class ServicesAggregator(MetricAggregator):
    """Портфель услуг: топ, выручка/кол-во по услугам, сочетания (упрощенно)."""

    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> Dict[str, Any]:
        # Берём child-таблицу Car wash appointment service
        rows = frappe.get_all(
            "Car wash appointment service",
            fields=["service", "service_name", "price"],
            filters={
                "parenttype": "Car wash appointment",
                "parent": ["in", [r["name"] for r in data if r.get("name")]],
            },
        )

        by_service: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            key = r.get("service") or r.get("service_name")
            if not key:
                continue
            s = by_service.setdefault(key, {"name": r.get("service_name") or key, "count": 0, "revenue": 0.0})
            s["count"] += 1
            s["revenue"] += float(r.get("price") or 0)

        top = sorted(by_service.values(), key=lambda x: (-x["revenue"], -x["count"]))[:20]
        return {
            "top": [
                {"service": i["name"], "count": i["count"], "revenue": round(i["revenue"], 2)}
                for i in top
            ]
        }

    def get_section_name(self) -> str:
        return "services"


