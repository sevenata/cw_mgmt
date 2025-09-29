# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/providers/base_provider.py
"""
Базовые классы для провайдеров данных.
"""

from typing import Any, Dict, List
from abc import ABC, abstractmethod
from ..base import ReportContext


class DataProvider(ABC):
    """Базовый класс для всех провайдеров данных"""
    
    @abstractmethod
    def fetch_data(self, context: ReportContext) -> List[Dict[str, Any]]:
        """Загружает данные для отчета"""
        pass


