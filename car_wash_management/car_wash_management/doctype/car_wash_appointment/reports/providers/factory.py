# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/providers/factory.py
"""
Фабрика для создания провайдеров данных.
"""

from typing import List
from .appointment_provider import AppointmentDataProvider
from .box_provider import BoxDataProvider
from .worker_provider import WorkerDataProvider
from .service_provider import ServiceDataProvider
from .payment_provider import PaymentDataProvider


class DataProviderFactory:
    """Фабрика для создания провайдеров данных"""
    
    @staticmethod
    def create_appointment_provider(fields: List[str] = None) -> AppointmentDataProvider:
        """Создает провайдер записей"""
        return AppointmentDataProvider(fields)
    
    @staticmethod
    def create_box_provider() -> BoxDataProvider:
        """Создает провайдер боксов"""
        return BoxDataProvider()
    
    @staticmethod
    def create_worker_provider() -> WorkerDataProvider:
        """Создает провайдер работников"""
        return WorkerDataProvider()
    
    @staticmethod
    def create_service_provider() -> ServiceDataProvider:
        """Создает провайдер услуг"""
        return ServiceDataProvider()
    
    @staticmethod
    def create_payment_provider() -> PaymentDataProvider:
        """Создает провайдер платежей"""
        return PaymentDataProvider()


