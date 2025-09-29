# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/special/__init__.py
"""
Специальные агрегаторы метрик: лаг оплаты и другие специфические метрики
"""

from .payment_lag import PaymentLagAggregator
from .forecast import ForecastAggregator
from .anomalies import AnomaliesAggregator

__all__ = [
    'PaymentLagAggregator',
    'ForecastAggregator',
    'AnomaliesAggregator'
]
