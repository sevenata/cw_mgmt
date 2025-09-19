# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/operational/queue.py
"""
Агрегатор метрик по очереди
"""

from typing import Any, Dict, List
from ...base import MetricAggregator, ReportContext


class QueueAggregator(MetricAggregator):
    """Очередь/вне очереди"""
    
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> Dict[str, Any]:
        out_cnt = sum(1 for r in data if int(r.get("out_of_turn") or 0) == 1)
        total = len(data)
        return {
            "out_of_turn_count": out_cnt,
            "rate_pct": round((out_cnt / total * 100.0) if total else 0.0, 2),
        }
    
    def get_section_name(self) -> str:
        return "queue"

