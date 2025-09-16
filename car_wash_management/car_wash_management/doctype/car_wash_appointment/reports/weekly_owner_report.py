# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/weekly_owner_report.py
"""
Недельный отчет владельца мойки.
Использует новую модульную архитектуру для легкого расширения функциональности.
"""

from __future__ import annotations
import frappe
from .service import ReportServiceFactory, WeeklyReportService
from .base import ReportConfiguration, ReportSection


# Создаем глобальный экземпляр сервиса
_report_service: WeeklyReportService = None


def _get_report_service() -> WeeklyReportService:
    """Получает или создает экземпляр сервиса отчетов"""
    global _report_service
    if _report_service is None:
        # Создаем конфигурацию по умолчанию
        config = ReportConfiguration()
        config.set_cache_ttl(300)  # 5 минут
        _report_service = ReportServiceFactory.create_weekly_service(config)
    return _report_service


@frappe.whitelist()
def get_weekly_owner_report(car_wash: str, date: str, sections: list = None) -> str:
    """
    Возвращает JSON с недельным отчётом по мойке.
    
    Использует новую модульную архитектуру с возможностью:
    - Легкого добавления новых метрик
    - Настройки секций отчета
    - Кэширования результатов
    - Расширения функциональности
    
    :param car_wash: имя/ID DocType 'Car wash'
    :param date: любая дата внутри нужной недели (YYYY-MM-DD)
    :param sections: список секций для включения в отчет (опционально)
    """
    service = _get_report_service()
    return service.generate_report(car_wash, date, sections)




@frappe.whitelist()
def get_available_sections() -> str:
    """Возвращает список доступных секций отчета"""
    sections = [
        {"value": section.value, "label": section.value.replace("_", " ").title()}
        for section in ReportSection
    ]
    
    return frappe.as_json({
        "sections": sections,
        "default_sections": [s.value for s in ReportConfiguration().sections]
    })


@frappe.whitelist()
def clear_report_cache(car_wash: str = None) -> str:
    """Очищает кэш отчетов"""
    try:
        service = _get_report_service()
        service.clear_cache(car_wash)
        
        message = f"Кэш очищен для мойки '{car_wash}'" if car_wash else "Весь кэш отчетов очищен"
        
        return frappe.as_json({
            "status": "success",
            "message": message
        })
        
    except Exception as e:
        return frappe.as_json({
            "status": "error",
            "message": f"Ошибка при очистке кэша: {str(e)}"
        })

