# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/operational/cancellations.py
"""
Агрегатор метрик по отменам
"""

from collections import defaultdict
from typing import Any, Dict, List
from ...base import MetricAggregator, ReportContext


class CancellationsAggregator(MetricAggregator):
    """Отмены и причины"""
    
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> Dict[str, Any]:
        total = len(data)
        cancelled = 0
        reasons = defaultdict(int)
        for r in data:
            reason = (r.get("cancellation_reason") or "").strip()
            if reason:
                cancelled += 1
                reasons[reason] += 1
        return {
            "cancelled": cancelled,
            "rate_pct": round((cancelled / total * 100.0) if total else 0.0, 2),
            "reasons": [
                {"reason": k, "count": v}
                for k, v in sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
        }
    
    def get_section_name(self) -> str:
        return "cancellations"

