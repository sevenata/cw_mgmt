# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/core/__init__.py
"""
Основные агрегаторы метрик: посещения, выручка, платежи
"""

from .visits import VisitsAggregator
from .revenue import RevenueAggregator
from .payments import PaymentsAggregator
from .price_control import PriceControlAggregator
from .tariffs import TariffsAggregator

__all__ = [
    'VisitsAggregator',
    'RevenueAggregator', 
    'PaymentsAggregator',
    'PriceControlAggregator',
    'TariffsAggregator'
]
