# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/base.py
"""
Базовые классы и интерфейсы для системы отчетов.
Обеспечивает расширяемость и единообразие архитектуры.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol
from enum import Enum


class ReportSection(Enum):
    """Типы секций отчета"""
    VISITS = "visits"
    REVENUE = "revenue"
    PAYMENTS = "payments"
    UTILIZATION = "utilization"
    BY_DAY = "by_day"
    STAFF = "staff"
    CANCELLATIONS = "cancellations"
    SCHEDULE = "schedule"
    QUEUE = "queue"
    BY_BOX = "by_box"
    BY_HOUR = "by_hour"
    PAYMENT_LAG = "payment_lag"
    CUSTOMERS = "customers"
    SERVICES = "services"
    PRICE_CONTROL = "price_control"
    TARIFFS = "tariffs"
    ANOMALIES = "anomalies"
    CAR_SEGMENT = "car_segment"
    BOX_CAPACITY_TYPE = "box_capacity_type"
    FORECAST = "forecast"


@dataclass
class WeekWindow:
    """Окно недели для анализа"""
    start: datetime
    end: datetime


@dataclass
class ReportContext:
    """Контекст выполнения отчета"""
    car_wash: str
    current_week: WeekWindow
    previous_week: WeekWindow
    generated_at: datetime


class DataProvider(Protocol):
    """Протокол для провайдеров данных"""
    
    def fetch_data(self, context: ReportContext) -> List[Dict[str, Any]]:
        """Загружает данные для отчета"""
        ...


class MetricAggregator(ABC):
    """Базовый класс для агрегаторов метрик"""
    
    @abstractmethod
    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> Dict[str, Any]:
        """Агрегирует данные в метрики"""
        pass
    
    @abstractmethod
    def get_section_name(self) -> str:
        """Возвращает название секции отчета"""
        pass


class ReportBuilder(ABC):
    """Базовый класс для билдеров отчетов"""
    
    @abstractmethod
    def build(self, context: ReportContext, sections: Dict[str, Any]) -> Dict[str, Any]:
        """Строит финальный отчет"""
        pass


class CacheManager(ABC):
    """Базовый класс для управления кэшем"""
    
    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        """Получает данные из кэша"""
        pass
    
    @abstractmethod
    def set(self, key: str, value: str, ttl_seconds: int = 300) -> None:
        """Сохраняет данные в кэш"""
        pass


class ReportConfiguration:
    """Конфигурация отчета"""
    
    def __init__(self):
        self.sections: List[ReportSection] = [
            ReportSection.VISITS,
            ReportSection.REVENUE,
            ReportSection.PAYMENTS,
            ReportSection.UTILIZATION,
            ReportSection.BY_DAY,
            ReportSection.STAFF,
            ReportSection.CANCELLATIONS,
            ReportSection.SCHEDULE,
            ReportSection.QUEUE,
            ReportSection.BY_BOX,
            ReportSection.BY_HOUR,
            ReportSection.PAYMENT_LAG,
            ReportSection.CUSTOMERS,
            ReportSection.SERVICES,
            ReportSection.PRICE_CONTROL,
            ReportSection.TARIFFS,
            ReportSection.ANOMALIES,
            ReportSection.CAR_SEGMENT,
            ReportSection.BOX_CAPACITY_TYPE,
            ReportSection.FORECAST,
        ]
        self.cache_ttl: int = 300  # 5 минут
        self.enable_caching: bool = True
    
    def add_section(self, section: ReportSection) -> 'ReportConfiguration':
        """Добавляет секцию в отчет"""
        if section not in self.sections:
            self.sections.append(section)
        return self
    
    def remove_section(self, section: ReportSection) -> 'ReportConfiguration':
        """Удаляет секцию из отчета"""
        if section in self.sections:
            self.sections.remove(section)
        return self
    
    def set_cache_ttl(self, ttl_seconds: int) -> 'ReportConfiguration':
        """Устанавливает время жизни кэша"""
        self.cache_ttl = ttl_seconds
        return self


class ReportRegistry:
    """Реестр для регистрации компонентов отчета"""
    
    def __init__(self):
        self._data_providers: Dict[str, DataProvider] = {}
        self._aggregators: Dict[ReportSection, MetricAggregator] = {}
        self._builders: Dict[str, ReportBuilder] = {}
        self._cache_managers: Dict[str, CacheManager] = {}
    
    def register_data_provider(self, name: str, provider: DataProvider) -> None:
        """Регистрирует провайдер данных"""
        self._data_providers[name] = provider
    
    def register_aggregator(self, section: ReportSection, aggregator: MetricAggregator) -> None:
        """Регистрирует агрегатор метрик"""
        self._aggregators[section] = aggregator
    
    def register_builder(self, name: str, builder: ReportBuilder) -> None:
        """Регистрирует билдер отчета"""
        self._builders[name] = builder
    
    def register_cache_manager(self, name: str, manager: CacheManager) -> None:
        """Регистрирует менеджер кэша"""
        self._cache_managers[name] = manager
    
    def get_data_provider(self, name: str) -> Optional[DataProvider]:
        """Получает провайдер данных"""
        return self._data_providers.get(name)
    
    def get_aggregator(self, section: ReportSection) -> Optional[MetricAggregator]:
        """Получает агрегатор метрик"""
        return self._aggregators.get(section)
    
    def get_builder(self, name: str) -> Optional[ReportBuilder]:
        """Получает билдер отчета"""
        return self._builders.get(name)
    
    def get_cache_manager(self, name: str) -> Optional[CacheManager]:
        """Получает менеджер кэша"""
        return self._cache_managers.get(name)


# Глобальный реестр
report_registry = ReportRegistry()
