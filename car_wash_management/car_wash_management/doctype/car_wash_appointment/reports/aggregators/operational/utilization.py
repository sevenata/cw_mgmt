# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/operational/utilization.py
"""
Агрегатор метрик по утилизации
"""

from typing import Any, Dict, List
import frappe
from ...base import MetricAggregator, ReportContext


class UtilizationAggregator(MetricAggregator):
    """Агрегатор метрик по утилизации"""
    
    def __init__(self, boxes_data: List[Dict[str, Any]]):
        self.boxes_data = boxes_data
    
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> Dict[str, Any]:
        """Агрегирует метрики утилизации"""
        busy_seconds_sum = 0.0
        
        for r in data:
            busy_seconds_sum += self._duration_seconds(r)
        
        boxes_count = max(1, len(self.boxes_data))
        capacity_hours = (context.current_week.end - context.current_week.start).total_seconds() * boxes_count / 3600.0
        busy_hours = busy_seconds_sum / 3600.0
        util_pct = (busy_hours / capacity_hours * 100.0) if capacity_hours > 0 else 0.0
        
        return {
            "boxes": boxes_count,
            "busy_hours": round(busy_hours, 2),
            "weekly_capacity_hours": round(capacity_hours, 2),
            "utilization_pct": round(util_pct, 2),
        }
    
    def _duration_seconds(self, row: Dict[str, Any]) -> float:
        """Вычисляет продолжительность работы"""
        ws = row.get("work_started_on")
        we = row.get("work_ended_on")
        ss = row.get("starts_on")
        se = row.get("ends_on")
        a = ws or ss
        b = we or se
        if not a or not b:
            return 0.0
        try:
            delta = frappe.utils.get_datetime(b) - frappe.utils.get_datetime(a)
            return max(0.0, delta.total_seconds())
        except Exception:
            return 0.0
    
    def get_section_name(self) -> str:
        return "utilization"
