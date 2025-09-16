# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/__init__.py
"""
Агрегаторы метрик для системы отчетов.
Каждый агрегатор отвечает за вычисление определенного типа метрик.
"""

# Импорты из основных метрик
from .core import (
    VisitsAggregator,
    RevenueAggregator,
    PaymentsAggregator,
    PriceControlAggregator,
    TariffsAggregator,
)

# Импорты из операционных метрик
from .operational import (
    UtilizationAggregator,
    ScheduleAggregator,
    QueueAggregator,
    CancellationsAggregator,
    BoxCapacityTypeAggregator,
)

# Импорты из аналитических метрик
from .analytics import (
    ByDayAggregator,
    ByBoxAggregator,
    ByHourAggregator,
    StaffAggregator,
    CustomersAggregator,
    ServicesAggregator,
    CarSegmentAggregator,
)

# Импорты из специальных метрик
from .special import (
    PaymentLagAggregator,
    ForecastAggregator,
)

# Фабрика агрегаторов
from .factory import AggregatorFactory

__all__ = [
    # Основные метрики
    'VisitsAggregator',
    'RevenueAggregator',
    'PaymentsAggregator',
    'PriceControlAggregator',
    'TariffsAggregator',
    
    # Операционные метрики
    'UtilizationAggregator',
    'ScheduleAggregator',
    'QueueAggregator',
    'CancellationsAggregator',
    'BoxCapacityTypeAggregator',
    
    # Аналитические метрики
    'ByDayAggregator',
    'ByBoxAggregator',
    'ByHourAggregator',
    'StaffAggregator',
    'CustomersAggregator',
    'ServicesAggregator',
    'CarSegmentAggregator',
    
    # Специальные метрики
    'PaymentLagAggregator',
    'ForecastAggregator',
    
    # Фабрика
    'AggregatorFactory'
]
