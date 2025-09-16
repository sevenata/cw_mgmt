"""Контроль цен/скидок"""

from typing import Any, Dict, List
import frappe
from ...base import MetricAggregator, ReportContext


class PriceControlAggregator(MetricAggregator):
    """Доля динамических цен и отклонение от базовой."""

    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> Dict[str, Any]:
        # Выгружаем позиции услуг недели
        appt_names = [r["name"] for r in data if r.get("name")]
        if not appt_names:
            return {"dynamic_share_pct": 0.0, "avg_deviation_pct": 0.0}

        rows = frappe.get_all(
            "Car wash appointment service",
            fields=["service", "price", "is_custom_price", "custom_price"],
            filters={"parent": ["in", appt_names]},
        )

        total = 0
        dynamic = 0
        deviations = []
        # Получим базовые цены услуг
        service_base = self._get_service_prices(list({r.get("service") for r in rows if r.get("service")}))

        for r in rows:
            total += 1
            base = float(service_base.get(r.get("service"), 0))
            price = float((r.get("custom_price") if int(r.get("is_custom_price") or 0) else r.get("price")) or 0)
            if int(r.get("is_custom_price") or 0):
                dynamic += 1
            if base > 0:
                deviations.append((price - base) / base * 100.0)

        avg_dev = sum(deviations) / len(deviations) if deviations else 0.0
        share = (dynamic / total * 100.0) if total else 0.0
        return {"dynamic_share_pct": round(share, 2), "avg_deviation_pct": round(avg_dev, 2)}

    def _get_service_prices(self, service_ids: List[str]) -> Dict[str, float]:
        if not service_ids:
            return {}
        rows = frappe.get_all(
            "Car wash service",
            fields=["name", "price"],
            filters={"name": ["in", service_ids]},
        )
        return {r["name"]: float(r.get("price") or 0) for r in rows}

    def get_section_name(self) -> str:
        return "price_control"


