"""Простой прогноз загрузки на следующую неделю.

Метод: усредняем по дням недели за последние 8 недель (если есть данные) 
и переносим на следующую неделю.
"""

from collections import defaultdict
from typing import Any, Dict, List
import datetime as _dt
import frappe
from ...base import MetricAggregator, ReportContext


class ForecastAggregator(MetricAggregator):
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> List[Dict[str, Any]]:
        # Используем историю за 8 недель до текущей
        start = context.current_week.start - _dt.timedelta(days=7 * 8)
        end = context.current_week.start
        rows = frappe.get_all(
            "Car wash appointment",
            fields=["starts_on"],
            filters={
                "car_wash": context.car_wash,
                "is_deleted": 0,
                "starts_on": ["between", [start, end]],
            },
            order_by="starts_on asc",
            limit=50000,
        )
        buckets = defaultdict(int)
        for r in rows:
            d = frappe.utils.get_datetime(r["starts_on"]).date()
            buckets[d.weekday()] += 1
        avg_by_weekday = {wd: (buckets.get(wd, 0) / 8.0) for wd in range(7)}

        # Следующая неделя
        next_week_start = context.current_week.end
        forecast = []
        for i in range(7):
            day = next_week_start + _dt.timedelta(days=i)
            wd = day.weekday()
            forecast.append({
                "date": day.isoformat(),
                "visits_forecast": round(avg_by_weekday.get(wd, 0), 2),
            })
        return forecast

    def get_section_name(self) -> str:
        return "forecast"


