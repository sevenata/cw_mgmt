# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/service.py
"""
Основной сервис для выполнения отчетов.
Обеспечивает высокоуровневый API для работы с отчетами.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import frappe
from .base import ReportContext, WeekWindow, ReportConfiguration, report_registry
from .providers import AppointmentDataProvider, BoxDataProvider
from .aggregators import UtilizationAggregator
from .builders import BuilderFactory


class WeeklyReportService:
    """Основной сервис для недельных отчетов"""
    
    def __init__(self, config: ReportConfiguration = None):
        self.config = config or ReportConfiguration()
        self._initialize_components()
    
    def _initialize_components(self):
        """Инициализирует компоненты системы"""
        from .registry import initialize_report_system
        initialize_report_system()
    
    def generate_report(self, car_wash: str, date: str, 
                       sections: List[str] = None) -> str:
        """
        Генерирует недельный отчет
        
        Args:
            car_wash: ID мойки
            date: Дата в формате YYYY-MM-DD
            sections: Список секций для включения в отчет
        
        Returns:
            JSON строка с отчетом
        """
        try:
            frappe.logger().info(f"Starting report generation for car_wash: {car_wash}, date: {date}")
            
            context = self._create_context(car_wash, date)
            sections = sections or [s.value for s in self.config.sections]
            
            frappe.logger().info(f"Report sections: {sections}")
            
            # Загружаем данные
            data = self._load_data(context)
            
            # Проверяем, что данные загружены
            current_count = len(data["current"])
            previous_count = len(data["previous"])
            frappe.logger().info(f"Loaded data - current week: {current_count} records, previous week: {previous_count} records")
            
            if not data["current"] and not data["previous"]:
                frappe.logger().warning(f"No data found for car_wash: {car_wash}, date: {date}")
            
            # Агрегируем метрики
            current_sections = self._aggregate_sections(data["current"], context, sections)

            # Используем контекст предыдущей недели для корректных расчётов (ёмкость, боксы и т.д.)
            prev_context = ReportContext(
                car_wash=context.car_wash,
                current_week=context.previous_week,
                previous_week=WeekWindow(
                    start=context.previous_week.start - timedelta(days=7),
                    end=context.previous_week.start,
                ),
                generated_at=context.generated_at,
            )
            previous_sections = self._aggregate_sections(data["previous"], prev_context, sections)
            
            frappe.logger().info(f"Successfully aggregated {len(current_sections)} current sections and {len(previous_sections)} previous sections")
            
            # Вычисляем дельты
            delta_sections = self._calculate_deltas(current_sections, previous_sections)
            
            # Строим отчет
            report_data = {
                "current": current_sections,
                "previous": previous_sections,
                "delta": delta_sections
            }
            
            # Получаем билдер и кэш-менеджер
            builder = report_registry.get_builder("weekly")
            cache_manager = report_registry.get_cache_manager("frappe")
            
            if not builder or not cache_manager:
                raise RuntimeError("Required components not registered")
            
            # Выполняем отчет
            from .builders import ReportService
            report_service = ReportService(cache_manager, builder)
            
            return report_service.execute_report(
                context, 
                report_data,
                use_cache=self.config.enable_caching,
                cache_ttl=self.config.cache_ttl,
                sections_list=sections
            )
            
        except Exception as e:
            frappe.log_error(f"Error generating report for car_wash: {car_wash}, date: {date}: {str(e)}", "WeeklyReportService")
            return frappe.as_json({
                "error": "Failed to generate report",
                "message": str(e),
                "car_wash": car_wash,
                "date": date
            })
    
    def _create_context(self, car_wash: str, date: str) -> ReportContext:
        """Создает контекст отчета"""
        ww = self._week_window(date)
        prev = WeekWindow(start=ww.start - timedelta(days=7), end=ww.start)
        
        return ReportContext(
            car_wash=car_wash,
            current_week=ww,
            previous_week=prev,
            generated_at=frappe.utils.now()
        )
    
    def _week_window(self, date_str: str) -> WeekWindow:
        """Вычисляет окно недели"""
        dt = frappe.utils.get_datetime(date_str)
        d0 = dt.date()
        monday = d0 - timedelta(days=d0.weekday())
        start = datetime.combine(monday, datetime.min.time())
        end = start + timedelta(days=7)
        return WeekWindow(start=start, end=end)
    
    def _load_data(self, context: ReportContext) -> Dict[str, List[Dict[str, Any]]]:
        """Загружает данные для обеих недель"""
        appointment_provider = AppointmentDataProvider()
        
        # Загружаем данные отдельно для каждой недели (более эффективно)
        current_appointments = appointment_provider.fetch_current_week_data(context)
        
        # Для предыдущей недели создаем отдельный контекст
        prev_context = ReportContext(
            car_wash=context.car_wash,
            current_week=context.previous_week,
            previous_week=WeekWindow(
                start=context.previous_week.start - timedelta(days=7),
                end=context.previous_week.start
            ),
            generated_at=context.generated_at
        )
        previous_appointments = appointment_provider.fetch_current_week_data(prev_context)
        
        return {
            "current": current_appointments,
            "previous": previous_appointments
        }
    
    def _aggregate_sections(self, appointments: List[Dict[str, Any]], 
                           context: ReportContext, sections: List[str]) -> Dict[str, Any]:
        """Агрегирует секции отчета"""
        result = {}
        
        # Загружаем боксы для утилизации
        box_provider = BoxDataProvider()
        boxes = box_provider.fetch_data(context)
        
        for section in sections:
            aggregator = self._get_aggregator(section, boxes)
            if aggregator:
                result[section] = aggregator.aggregate(appointments, context)
        
        return result
    
    def _get_aggregator(self, section: str, boxes: List[Dict[str, Any]]):
        """Получает агрегатор для секции"""
        from .base import ReportSection
        
        try:
            section_enum = ReportSection(section)
        except ValueError:
            # Неизвестная секция - пропускаем
            return None
        
        if section_enum == ReportSection.UTILIZATION:
            return UtilizationAggregator(boxes)
        if section_enum == ReportSection.BOX_CAPACITY_TYPE:
            from .aggregators import BoxCapacityTypeAggregator
            return BoxCapacityTypeAggregator(boxes)
        
        return report_registry.get_aggregator(section_enum)
    
    def _calculate_deltas(self, current: Dict[str, Any], 
                         previous: Dict[str, Any]) -> Dict[str, Any]:
        """Вычисляет дельты между текущими и предыдущими метриками"""
        deltas = {}
        
        # Список полей для сравнения
        comparison_fields = [
            "visits.total",
            "revenue.grand_total",
            "revenue.avg_check",
            "utilization.utilization_pct"
        ]
        
        for field in comparison_fields:
            curr_val = self._get_nested_value(current, field)
            prev_val = self._get_nested_value(previous, field)
            
            if curr_val is not None and prev_val is not None:
                diff = curr_val - prev_val
                pct = (diff / prev_val * 100.0) if prev_val != 0 else None
                
                deltas[field.replace(".", "_")] = {
                    "abs": round(diff, 2),
                    "pct": None if pct is None else round(pct, 2)
                }
        
        return deltas
    
    def _get_nested_value(self, data: Dict[str, Any], field: str) -> Optional[float]:
        """Получает значение по вложенному ключу"""
        keys = field.split('.')
        value = data
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        
        return float(value) if isinstance(value, (int, float)) else None
    
    
    def clear_cache(self, car_wash: str = None):
        """Очищает кэш отчетов"""
        cache_manager = report_registry.get_cache_manager("frappe")
        if cache_manager:
            from .builders import ReportService
            report_service = ReportService(cache_manager, None)
            report_service.clear_cache(car_wash)


# Фабрика сервисов
class ReportServiceFactory:
    """Фабрика для создания сервисов отчетов"""
    
    @staticmethod
    def create_weekly_service(config: ReportConfiguration = None) -> WeeklyReportService:
        """Создает сервис недельных отчетов"""
        return WeeklyReportService(config)
    
    @staticmethod
    def create_custom_service(config: ReportConfiguration) -> WeeklyReportService:
        """Создает сервис с пользовательской конфигурацией"""
        return WeeklyReportService(config)
