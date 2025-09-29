# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/analytics/__init__.py
"""
Аналитические агрегаторы метрик: срезы по дням, боксам, часам, персоналу
"""

from .by_day import ByDayAggregator
from .by_box import ByBoxAggregator
from .by_hour import ByHourAggregator
from .staff import StaffAggregator
from .customers import CustomersAggregator
from .services import ServicesAggregator
from .car_segment import CarSegmentAggregator

__all__ = [
    'ByDayAggregator',
    'ByBoxAggregator',
    'ByHourAggregator',
    'StaffAggregator',
    'CustomersAggregator',
    'ServicesAggregator',
    'CarSegmentAggregator'
]
