"""Аномалии/риски"""

from typing import Any, Dict, List
import frappe
from ...base import MetricAggregator, ReportContext


class AnomaliesAggregator(MetricAggregator):
    """Выделяет подозрительные визиты"""

    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> Dict[str, Any]:
        suspicious = []
        long_jobs = 0
        short_jobs = 0
        unpaid_with_end = 0
        paid_after = 0

        for r in data:
            ws = r.get("work_started_on") or r.get("starts_on")
            we = r.get("work_ended_on") or r.get("ends_on")
            dur_min = 0
            if ws and we:
                dur_min = (frappe.utils.get_datetime(we) - frappe.utils.get_datetime(ws)).total_seconds() / 60.0
            if dur_min > 240:
                long_jobs += 1
            if 0 < dur_min < 10:
                short_jobs += 1
            if r.get("payment_status") != "Paid" and we:
                unpaid_with_end += 1
            if r.get("payment_status") == "Paid" and we and r.get("payment_received_on"):
                if frappe.utils.get_datetime(r["payment_received_on"]) > frappe.utils.get_datetime(we) + frappe.utils.timedelta(minutes=30):
                    paid_after += 1

        return {
            "long_jobs": long_jobs,
            "short_jobs": short_jobs,
            "unpaid_but_finished": unpaid_with_end,
            "payments_after_30m": paid_after,
        }

    def get_section_name(self) -> str:
        return "anomalies"


