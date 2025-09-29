# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/analytics/staff.py
"""
Агрегатор метрик по персоналу
"""

from collections import defaultdict
from typing import Any, Dict, List
from ...base import MetricAggregator, ReportContext


class StaffAggregator(MetricAggregator):
    """Агрегатор метрик по персоналу"""
    
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> Dict[str, Any]:
        """Агрегирует метрики персонала"""
        staff = defaultdict(lambda: {"worker_name": None, "visits": 0, "revenue_total": 0.0, "reward_total": 0.0})
        
        for r in data:
            wkey = r.get("car_wash_worker") or "Unknown"
            staff[wkey]["worker_name"] = r.get("car_wash_worker_name") or wkey
            staff[wkey]["visits"] += 1
            revenue_value = r.get("services_total")
            if revenue_value is None:
                revenue_value = r.get("grand_total")
            staff[wkey]["revenue_total"] += float(revenue_value or 0)
            staff[wkey]["reward_total"] += float(r.get("staff_reward_total") or 0)
        
        return [
            {
                "worker": key,
                "worker_name": data["worker_name"],
                "visits": data["visits"],
                "revenue_total": round(data["revenue_total"], 2),
                "reward_total": round(data["reward_total"], 2),
            }
            for key, data in sorted(staff.items(), key=lambda kv: (-kv[1]["revenue_total"], kv[0]))
        ]
    
    def get_section_name(self) -> str:
        return "staff"


