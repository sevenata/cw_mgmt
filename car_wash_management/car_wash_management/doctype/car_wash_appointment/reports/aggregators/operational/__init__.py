# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/operational/__init__.py
"""
Операционные агрегаторы метрик: утилизация, расписание, очередь, отмены
"""

from .utilization import UtilizationAggregator
from .schedule import ScheduleAggregator
from .queue import QueueAggregator
from .cancellations import CancellationsAggregator
from .box_capacity_type import BoxCapacityTypeAggregator

__all__ = [
    'UtilizationAggregator',
    'ScheduleAggregator',
    'QueueAggregator',
    'CancellationsAggregator'
]
