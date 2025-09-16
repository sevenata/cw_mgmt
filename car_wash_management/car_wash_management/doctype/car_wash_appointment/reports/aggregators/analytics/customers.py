# car_wash_management/.../aggregators/analytics/customers.py
"""
Клиентские метрики: LTV, удержание/когорты, Repeat‑30/60/90.

Примечание: для легковесности считаем метрики на подмножестве — 
только среди клиентов текущей недели. Поведение можно расширить позже.
"""

from typing import Any, Dict, List, Set
import frappe
from ...base import MetricAggregator, ReportContext


class CustomersAggregator(MetricAggregator):
    """Клиентские метрики недели"""

    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> Dict[str, Any]:
        customers: Set[str] = set(r.get("customer") for r in data if r.get("customer"))
        if not customers:
            return {
                "customers": 0,
                "ltv_avg": 0.0,
                "repeat": {"d30": 0.0, "d60": 0.0, "d90": 0.0},
                "cohorts": [],
            }

        customers_list = list(customers)

        # LTV (упрощенно): средняя суммарная выручка на клиента за всё время
        ltv_total = self._calc_total_revenue_for_customers(customers_list)
        ltv_avg = (ltv_total / len(customers_list)) if customers_list else 0.0

        # Repeat-30/60/90: доля клиентов недели, у которых были визиты в предыдущие N дней
        r30 = self._calc_repeat_ratio(customers_list, context, days=30)
        r60 = self._calc_repeat_ratio(customers_list, context, days=60)
        r90 = self._calc_repeat_ratio(customers_list, context, days=90)

        return {
            "customers": len(customers_list),
            "ltv_avg": round(ltv_avg, 2),
            "repeat": {
                "d30": round(r30, 2),
                "d60": round(r60, 2),
                "d90": round(r90, 2),
            },
            # Заглушка для когорт — можно развить позже
            "cohorts": [],
        }

    def _calc_total_revenue_for_customers(self, customers: List[str]) -> float:
        rows = frappe.get_all(
            "Car wash appointment",
            fields=["customer", "sum(grand_total) as total"],
            filters={"customer": ["in", customers], "is_deleted": 0},
            group_by="customer",
        )
        return float(sum(float(r.get("total") or 0) for r in rows))

    def _calc_repeat_ratio(self, customers: List[str], context: ReportContext, days: int) -> float:
        import datetime as _dt
        start = context.current_week.start - _dt.timedelta(days=days)
        end = context.current_week.start
        rows = frappe.get_all(
            "Car wash appointment",
            fields=["distinct customer"],
            filters={
                "customer": ["in", customers],
                "is_deleted": 0,
                "starts_on": ["between", [start, end]],
            },
        )
        return (len(rows) / len(customers) * 100.0) if customers else 0.0

    def get_section_name(self) -> str:
        return "customers"


