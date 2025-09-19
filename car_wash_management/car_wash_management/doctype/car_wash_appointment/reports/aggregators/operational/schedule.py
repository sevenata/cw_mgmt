# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/operational/schedule.py
"""
Агрегатор метрик по точности расписания
"""

from typing import Any, Dict, List
import frappe
from ...base import MetricAggregator, ReportContext


class ScheduleAggregator(MetricAggregator):
    """Точность расписания: опоздания/переработки"""
    
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> Dict[str, Any]:
        late_cnt = 0
        early_cnt = 0
        late_minutes_total = 0.0
        over_minutes_total = 0.0
        for r in data:
            ss = r.get("starts_on")
            ws = r.get("work_started_on")
            se = r.get("ends_on")
            we = r.get("work_ended_on")
            if ss and ws:
                diff = (frappe.utils.get_datetime(ws) - frappe.utils.get_datetime(ss)).total_seconds() / 60.0
                if diff > 1:  # опоздание более 1 минуты
                    late_cnt += 1
                    late_minutes_total += diff
                elif diff < -1:  # старт раньше графика
                    early_cnt += 1
            if se and we:
                diff2 = (frappe.utils.get_datetime(we) - frappe.utils.get_datetime(se)).total_seconds() / 60.0
                if diff2 > 1:
                    over_minutes_total += diff2
        total = len(data)
        return {
            "on_time_rate_pct": round(((total - late_cnt) / total * 100.0) if total else 0.0, 2),
            "late_count": late_cnt,
            "avg_late_min": round((late_minutes_total / late_cnt) if late_cnt else 0.0, 2),
            "early_start_count": early_cnt,
            "overrun_minutes_total": round(over_minutes_total, 2),
        }
    
    def get_section_name(self) -> str:
        return "schedule"

