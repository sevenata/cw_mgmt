# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/aggregators/factory.py
"""
Фабрика для создания агрегаторов
"""

from typing import Any, Dict, List
from .core import VisitsAggregator, RevenueAggregator, PaymentsAggregator, PriceControlAggregator, TariffsAggregator
from .operational import UtilizationAggregator, ScheduleAggregator, QueueAggregator, CancellationsAggregator, BoxCapacityTypeAggregator
from .analytics import ByDayAggregator, ByBoxAggregator, ByHourAggregator, StaffAggregator, CustomersAggregator, ServicesAggregator, CarSegmentAggregator
from .special import PaymentLagAggregator, ForecastAggregator


class AggregatorFactory:
    """Фабрика для создания агрегаторов"""
    
    @staticmethod
    def create_visits_aggregator() -> VisitsAggregator:
        return VisitsAggregator()
    
    @staticmethod
    def create_revenue_aggregator() -> RevenueAggregator:
        return RevenueAggregator()
    
    @staticmethod
    def create_payments_aggregator() -> PaymentsAggregator:
        return PaymentsAggregator()
    
    @staticmethod
    def create_utilization_aggregator(boxes_data: List[Dict[str, Any]]) -> UtilizationAggregator:
        return UtilizationAggregator(boxes_data)
    
    @staticmethod
    def create_by_day_aggregator() -> ByDayAggregator:
        return ByDayAggregator()
    
    @staticmethod
    def create_staff_aggregator() -> StaffAggregator:
        return StaffAggregator()
    
    @staticmethod
    def create_cancellations_aggregator() -> CancellationsAggregator:
        return CancellationsAggregator()
    
    @staticmethod
    def create_schedule_aggregator() -> ScheduleAggregator:
        return ScheduleAggregator()
    
    @staticmethod
    def create_queue_aggregator() -> QueueAggregator:
        return QueueAggregator()
    
    @staticmethod
    def create_by_box_aggregator() -> ByBoxAggregator:
        return ByBoxAggregator()
    
    @staticmethod
    def create_by_hour_aggregator() -> ByHourAggregator:
        return ByHourAggregator()
    
    @staticmethod
    def create_payment_lag_aggregator() -> PaymentLagAggregator:
        return PaymentLagAggregator()

    @staticmethod
    def create_customers_aggregator() -> CustomersAggregator:
        return CustomersAggregator()
    
    @staticmethod
    def create_services_aggregator() -> ServicesAggregator:
        return ServicesAggregator()
    
    @staticmethod
    def create_price_control_aggregator() -> PriceControlAggregator:
        return PriceControlAggregator()
    
    @staticmethod
    def create_tariffs_aggregator() -> TariffsAggregator:
        return TariffsAggregator()
    
    @staticmethod
    def create_car_segment_aggregator() -> CarSegmentAggregator:
        return CarSegmentAggregator()
    
    @staticmethod
    def create_box_capacity_type_aggregator(boxes: List[Dict[str, Any]]) -> BoxCapacityTypeAggregator:
        return BoxCapacityTypeAggregator(boxes)
    
    @staticmethod
    def create_forecast_aggregator() -> ForecastAggregator:
        return ForecastAggregator()
