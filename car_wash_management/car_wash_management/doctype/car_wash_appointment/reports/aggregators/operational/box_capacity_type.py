"""Пропускная способность по типу бокса"""

from collections import defaultdict
from typing import Any, Dict, List
import frappe
from ...base import MetricAggregator, ReportContext


class BoxCapacityTypeAggregator(MetricAggregator):
    def __init__(self, boxes: List[Dict[str, Any]]):
        self.boxes = boxes

    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> List[Dict[str, Any]]:
        # Группируем боксы по type
        type_to_boxes = defaultdict(list)
        for b in self.boxes:
            type_to_boxes[(b.get("type") or "Unknown")].append(b["name"])

        # Занятое время по типам
        busy_seconds_by_type = defaultdict(float)
        for r in data:
            bname = r.get("box")
            if not bname:
                continue
            btype = None
            for t, arr in type_to_boxes.items():
                if bname in arr:
                    btype = t
                    break
            if not btype:
                btype = "Unknown"
            ws = r.get("work_started_on") or r.get("starts_on")
            we = r.get("work_ended_on") or r.get("ends_on")
            if ws and we:
                busy_seconds_by_type[btype] += (frappe.utils.get_datetime(we) - frappe.utils.get_datetime(ws)).total_seconds()

        # Емкость недели на тип
        total_seconds_week = (context.current_week.end - context.current_week.start).total_seconds()
        res = []
        for t, arr in type_to_boxes.items():
            capacity_hours = total_seconds_week * max(1, len(arr)) / 3600.0
            busy_hours = busy_seconds_by_type.get(t, 0.0) / 3600.0
            util_pct = (busy_hours / capacity_hours * 100.0) if capacity_hours else 0.0
            res.append({
                "type": t,
                "boxes": len(arr),
                "busy_hours": round(busy_hours, 2),
                "capacity_hours": round(capacity_hours, 2),
                "utilization_pct": round(util_pct, 2),
            })
        return sorted(res, key=lambda x: (-x["utilization_pct"], -x["busy_hours"]))

    def get_section_name(self) -> str:
        return "box_capacity_type"


