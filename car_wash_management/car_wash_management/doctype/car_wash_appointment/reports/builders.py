# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/builders.py
"""
Билдеры отчетов и менеджеры кэша.
Обеспечивают построение финальных отчетов и управление кэшированием.
"""

from typing import Any, Dict, Optional, List
import frappe
from .base import ReportBuilder, CacheManager, ReportContext


class FrappeCacheManager(CacheManager):
    """Менеджер кэша на основе Frappe Cache"""
    
    def get(self, key: str) -> Optional[str]:
        """Получает данные из кэша Frappe"""
        return frappe.cache().get_value(key)
    
    def set(self, key: str, value: str, ttl_seconds: int = 300) -> None:
        """Сохраняет данные в кэш Frappe"""
        frappe.cache().set_value(key, value, expires_in_sec=ttl_seconds)


class WeeklyReportBuilder(ReportBuilder):
    """Билдер для недельных отчетов"""
    
    def build(self, context: ReportContext, sections: Dict[str, Any]) -> Dict[str, Any]:
        """Строит финальный недельный отчет"""
        return {
            "car_wash": context.car_wash,
            "week": {
                "start": context.current_week.start.isoformat(),
                "end": context.current_week.end.isoformat()
            },
            "previous_week": {
                "start": context.previous_week.start.isoformat(),
                "end": context.previous_week.end.isoformat()
            },
            "current": sections.get("current", {}),
            "previous": sections.get("previous", {}),
            "delta": sections.get("delta", {}),
            "generated_at": context.generated_at,
        }


class ComparisonReportBuilder(ReportBuilder):
    """Билдер для отчетов с сравнением"""
    
    def __init__(self, comparison_fields: list = None):
        self.comparison_fields = comparison_fields or [
            "visits_total",
            "revenue_grand_total", 
            "avg_check",
            "utilization_pct"
        ]
    
    def build(self, context: ReportContext, sections: Dict[str, Any]) -> Dict[str, Any]:
        """Строит отчет с сравнением метрик"""
        current = sections.get("current", {})
        previous = sections.get("previous", {})
        
        # Вычисляем дельты
        delta = self._calculate_deltas(current, previous)
        
        return {
            "car_wash": context.car_wash,
            "period": {
                "current": {
                    "start": context.current_week.start.isoformat(),
                    "end": context.current_week.end.isoformat()
                },
                "previous": {
                    "start": context.previous_week.start.isoformat(),
                    "end": context.previous_week.end.isoformat()
                }
            },
            "current": current,
            "previous": previous,
            "delta": delta,
            "generated_at": context.generated_at,
        }
    
    def _calculate_deltas(self, current: Dict[str, Any], previous: Dict[str, Any]) -> Dict[str, Any]:
        """Вычисляет дельты между текущими и предыдущими метриками"""
        deltas = {}
        
        for field in self.comparison_fields:
            curr_val = self._get_nested_value(current, field)
            prev_val = self._get_nested_value(previous, field)
            
            if curr_val is not None and prev_val is not None:
                diff = curr_val - prev_val
                pct = (diff / prev_val * 100.0) if prev_val != 0 else None
                
                deltas[field] = {
                    "abs": round(diff, 2),
                    "pct": None if pct is None else round(pct, 2)
                }
        
        return deltas
    
    def _get_nested_value(self, data: Dict[str, Any], field: str) -> Optional[float]:
        """Получает значение по вложенному ключу (например, 'visits.total')"""
        keys = field.split('.')
        value = data
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        
        return float(value) if isinstance(value, (int, float)) else None




class ReportService:
    """Сервис для выполнения отчетов"""
    
    def __init__(self, cache_manager: CacheManager, report_builder: ReportBuilder):
        self.cache_manager = cache_manager
        self.report_builder = report_builder
    
    def execute_report(self, context: ReportContext, sections: Dict[str, Any], 
                      use_cache: bool = True, cache_ttl: int = 300, 
                      sections_list: List[str] = None) -> str:
        """Выполняет отчет с опциональным кэшированием"""
        
        if use_cache:
            cache_key = self._generate_cache_key(context, sections_list)
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                return cached_result
        
        # Строим отчет
        report_data = self.report_builder.build(context, sections)
        result = frappe.as_json(report_data, ensure_ascii=False, indent=2)
        
        # Кэшируем результат
        if use_cache:
            self.cache_manager.set(cache_key, result, cache_ttl)
        
        return result
    
    def _generate_cache_key(self, context: ReportContext, sections: List[str] = None) -> str:
        """Генерирует ключ кэша на основе контекста и секций"""
        import hashlib
        
        # Создаем хэш секций для уникальности ключа
        sections_str = ",".join(sorted(sections or []))
        sections_hash = hashlib.md5(sections_str.encode()).hexdigest()[:8]
        
        return f"weekly_report_{context.car_wash}_{context.current_week.start.date()}_{sections_hash}"
    
    def clear_cache(self, car_wash: str = None) -> None:
        """Очищает кэш отчетов"""
        if car_wash:
            # Очищаем кэш для конкретной мойки
            pattern = f"weekly_report_{car_wash}_*"
            # В реальной реализации нужно использовать более сложную логику очистки
            pass
        else:
            # Очищаем весь кэш отчетов
            pattern = "weekly_report_*"
            # В реальной реализации нужно использовать более сложную логику очистки
            pass


# Фабрика билдеров
class BuilderFactory:
    """Фабрика для создания билдеров и менеджеров"""
    
    @staticmethod
    def create_frappe_cache_manager() -> FrappeCacheManager:
        """Создает менеджер кэша Frappe"""
        return FrappeCacheManager()
    
    @staticmethod
    def create_weekly_report_builder() -> WeeklyReportBuilder:
        """Создает билдер недельных отчетов"""
        return WeeklyReportBuilder()
    
    @staticmethod
    def create_comparison_report_builder(comparison_fields: list = None) -> ComparisonReportBuilder:
        """Создает билдер отчетов с сравнением"""
        return ComparisonReportBuilder(comparison_fields)
    
    
    @staticmethod
    def create_report_service(cache_manager: CacheManager = None, 
                            report_builder: ReportBuilder = None) -> ReportService:
        """Создает сервис отчетов"""
        cache_manager = cache_manager or BuilderFactory.create_frappe_cache_manager()
        report_builder = report_builder or BuilderFactory.create_weekly_report_builder()
        return ReportService(cache_manager, report_builder)
