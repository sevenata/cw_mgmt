# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/providers/__init__.py
"""
Провайдеры данных для системы отчетов.
"""

from .base_provider import DataProvider
from .appointment_provider import AppointmentDataProvider
from .box_provider import BoxDataProvider
from .worker_provider import WorkerDataProvider
from .service_provider import ServiceDataProvider
from .payment_provider import PaymentDataProvider
from .factory import DataProviderFactory

__all__ = [
    "DataProvider",
    "AppointmentDataProvider",
    "BoxDataProvider", 
    "WorkerDataProvider",
    "ServiceDataProvider",
    "PaymentDataProvider",
    "DataProviderFactory",
]


