# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/registry.py
"""
Регистрация и конфигурация компонентов системы отчетов.
Обеспечивает легкое добавление новых метрик и провайдеров.
"""

from .base import report_registry, ReportSection, ReportConfiguration
from .providers import (
    DataProviderFactory, 
    AppointmentDataProvider, 
    BoxDataProvider,
    WorkerDataProvider,
    ServiceDataProvider,
    PaymentDataProvider
)
from .aggregators import (
    AggregatorFactory,
    VisitsAggregator,
    RevenueAggregator,
    PaymentsAggregator,
    UtilizationAggregator,
    ByDayAggregator,
    StaffAggregator,
    CancellationsAggregator,
    ScheduleAggregator,
    QueueAggregator,
    ByBoxAggregator,
    ByHourAggregator,
    PaymentLagAggregator,
    CustomersAggregator,
    ServicesAggregator,
    PriceControlAggregator,
    TariffsAggregator,
    CarSegmentAggregator,
    BoxCapacityTypeAggregator,
    ForecastAggregator,
)
from .builders import (
    BuilderFactory,
    FrappeCacheManager,
    WeeklyReportBuilder,
    ComparisonReportBuilder
)


def register_default_components():
    """Регистрирует стандартные компоненты системы отчетов"""
    
    # Регистрируем провайдеры данных
    report_registry.register_data_provider(
        "appointments", 
        DataProviderFactory.create_appointment_provider()
    )
    report_registry.register_data_provider(
        "boxes", 
        DataProviderFactory.create_box_provider()
    )
    report_registry.register_data_provider(
        "workers", 
        DataProviderFactory.create_worker_provider()
    )
    report_registry.register_data_provider(
        "services", 
        DataProviderFactory.create_service_provider()
    )
    report_registry.register_data_provider(
        "payments", 
        DataProviderFactory.create_payment_provider()
    )
    
    # Регистрируем агрегаторы
    report_registry.register_aggregator(
        ReportSection.VISITS,
        AggregatorFactory.create_visits_aggregator()
    )
    report_registry.register_aggregator(
        ReportSection.REVENUE,
        AggregatorFactory.create_revenue_aggregator()
    )
    report_registry.register_aggregator(
        ReportSection.PAYMENTS,
        AggregatorFactory.create_payments_aggregator()
    )
    report_registry.register_aggregator(
        ReportSection.BY_DAY,
        AggregatorFactory.create_by_day_aggregator()
    )
    report_registry.register_aggregator(
        ReportSection.STAFF,
        AggregatorFactory.create_staff_aggregator()
    )
    report_registry.register_aggregator(
        ReportSection.CANCELLATIONS,
        AggregatorFactory.create_cancellations_aggregator()
    )
    report_registry.register_aggregator(
        ReportSection.SCHEDULE,
        AggregatorFactory.create_schedule_aggregator()
    )
    report_registry.register_aggregator(
        ReportSection.QUEUE,
        AggregatorFactory.create_queue_aggregator()
    )
    report_registry.register_aggregator(
        ReportSection.BY_BOX,
        AggregatorFactory.create_by_box_aggregator()
    )
    report_registry.register_aggregator(
        ReportSection.BY_HOUR,
        AggregatorFactory.create_by_hour_aggregator()
    )
    report_registry.register_aggregator(
        ReportSection.PAYMENT_LAG,
        AggregatorFactory.create_payment_lag_aggregator()
    )
    report_registry.register_aggregator(
        ReportSection.FORECAST,
        AggregatorFactory.create_forecast_aggregator()
    )
    report_registry.register_aggregator(
        ReportSection.CUSTOMERS,
        AggregatorFactory.create_customers_aggregator()
    )
    report_registry.register_aggregator(
        ReportSection.SERVICES,
        AggregatorFactory.create_services_aggregator()
    )
    report_registry.register_aggregator(
        ReportSection.PRICE_CONTROL,
        AggregatorFactory.create_price_control_aggregator()
    )
    report_registry.register_aggregator(
        ReportSection.TARIFFS,
        AggregatorFactory.create_tariffs_aggregator()
    )
    report_registry.register_aggregator(
        ReportSection.CAR_SEGMENT,
        AggregatorFactory.create_car_segment_aggregator()
    )
    # BOX_CAPACITY_TYPE создается в сервисе, т.к. требует список боксов при инициализации
    
    # Регистрируем билдеры
    report_registry.register_builder(
        "weekly",
        BuilderFactory.create_weekly_report_builder()
    )
    report_registry.register_builder(
        "comparison",
        BuilderFactory.create_comparison_report_builder()
    )
    
    # Регистрируем менеджер кэша
    report_registry.register_cache_manager(
        "frappe",
        BuilderFactory.create_frappe_cache_manager()
    )


def create_default_configuration() -> ReportConfiguration:
    """Создает конфигурацию по умолчанию"""
    config = ReportConfiguration()
    config.set_cache_ttl(300)  # 5 минут
    return config






# Инициализация системы
def initialize_report_system():
    """Инициализирует систему отчетов со всеми компонентами"""
    register_default_components()
    return create_default_configuration()
