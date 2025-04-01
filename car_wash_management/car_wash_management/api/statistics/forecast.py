import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import Count, Date
from datetime import datetime, timedelta
from typing import Optional

@frappe.whitelist()
def get_daily_orders_forecast(
    forecast_date: datetime,
    car_wash_id: Optional[str] = None,
    days_ahead: int = 7
):
    """
    Метод рассчитывает прогноз количества записей (Car wash appointment)
    на указанные дни вперёд, исходя из среднего показателя за последние 30 дней.

    :param forecast_date: Дата (и время), с которой начинаем строить прогноз.
    :param car_wash_id: Идентификатор конкретной автомойки (Car wash), если требуется
                        сделать прогноз только по ней. Если None – по всем автомойкам.
    :param days_ahead: На сколько дней вперёд делаем прогноз. По умолчанию 7.
    :return: Список словарей формата:
        [
            {
                "date": "2025-04-01",
                "forecast_appointments": 5
            },
            ...
        ]
    """
    CarWashAppointment = DocType("Car wash appointment")

    # Формируем условие выборки для исторических данных
    # Берём записи не позднее forecast_date, чтобы не использовать будущее
    # Также исключаем помеченные как удалённые (is_deleted=1)
    conditions = (
        (CarWashAppointment.is_deleted == 0)
        & (CarWashAppointment.starts_on < forecast_date)
    )

    # Если указан конкретный car_wash_id – добавляем условие
    if car_wash_id:
        conditions &= (CarWashAppointment.car_wash == car_wash_id)

    # Для примера возьмём историю за последние 30 дней
    start_date = forecast_date - timedelta(days=30)
    conditions &= (CarWashAppointment.starts_on >= start_date)

    # Строим запрос для получения количества записей по датам
    query = (
        frappe.qb.from_(CarWashAppointment)
        .select(
            Date(CarWashAppointment.starts_on).as_("date"),
            Count("*").as_("total_appointments")
        )
        .where(conditions)
        .groupby(Date(CarWashAppointment.starts_on))
    )

    # Выполняем запрос
    daily_counts = query.run(as_dict=True)

    # Считаем среднее количество записей в день
    if not daily_counts:
        avg_daily = 0
    else:
        total_appointments = sum(row["total_appointments"] for row in daily_counts)
        days_counted = len(daily_counts)
        avg_daily = total_appointments / days_counted

    # Формируем список с прогнозом на дни вперёд
    forecast_data = []
    for i in range(days_ahead):
        day = forecast_date + timedelta(days=i)
        forecast_data.append({
            "date": day.date().isoformat(),
            # Округляем до ближайшего целого, чтобы прогноз был в штуках
            "forecast_appointments": round(avg_daily)
        })

    return forecast_data
