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
    Прогноз количества записей (Car wash appointment) на основе статистики
    по дням недели. Сначала собирается статистика по историческим данным (за
    последние 60 дней), затем для каждого дня недели рассчитывается среднее.
    В итоге при формировании прогноза на каждый из days_ahead дней смотрим,
    какой это день недели, и подставляем соответствующее среднее значение.

    :param forecast_date: Дата (и время), с которой начинаем прогноз.
    :param car_wash_id: Если указан, прогноз строится только по записям конкретной автомойки.
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

    # Берём исторические данные за последние 60 дней (при желании число можно менять)
    history_days = 60
    start_date = forecast_date - timedelta(days=history_days)

    # Общие условия: не удалённые записи, дата раньше forecast_date
    conditions = (
        (CarWashAppointment.is_deleted == 0)
        & (CarWashAppointment.starts_on < forecast_date)
        & (CarWashAppointment.starts_on >= start_date)
    )

    # Если нужен прогноз по конкретной автомойке, добавляем условие
    if car_wash_id:
        conditions &= (CarWashAppointment.car_wash == car_wash_id)

    # Считаем количество записей по каждому календарному дню
    query = (
        frappe.qb.from_(CarWashAppointment)
        .select(
            Date(CarWashAppointment.starts_on).as_("date"),
            Count("*").as_("total_appointments")
        )
        .where(conditions)
        .groupby(Date(CarWashAppointment.starts_on))
    )

    daily_counts = query.run(as_dict=True)

    # Приводим daily_counts к виду:
    # [
    #   {"date": "2025-03-01", "total_appointments": 5},
    #   {"date": "2025-03-02", "total_appointments": 3},
    #   ...
    # ]

    # Словарь для статистики по дням недели: day_of_week -> {"count": суммарное количество, "days": число дат}
    # В Python Monday=0, Sunday=6 (weekday() возвращает 0..6).
    day_of_week_stats = {i: {"count": 0, "days": 0} for i in range(7)}

    for row in daily_counts:
        # row["date"] – это объект типа date или str (зависит от версии Frappe),
        # но чаще всего приходит как строка вида '2025-03-01'. Приведём к дате.
        row_date = (
            row["date"] if isinstance(row["date"], datetime) else datetime.strptime(str(row["date"]), "%Y-%m-%d")
        )
        dow = row_date.weekday()  # Monday=0, ... Sunday=6
        day_of_week_stats[dow]["count"] += row["total_appointments"]
        day_of_week_stats[dow]["days"] += 1

    # Теперь вычислим среднее для каждого дня недели
    # Если по какому-то дню недели нет записей, там так и останется count=0, days=0
    day_of_week_avg = {}
    for dow, vals in day_of_week_stats.items():
        if vals["days"] > 0:
            day_of_week_avg[dow] = vals["count"] / vals["days"]
        else:
            day_of_week_avg[dow] = 0  # Можно вместо 0 взять общий средний, если хотимfallback

    # На случай, если вообще нет исторических данных, найдём «глобальное» среднее
    total_all = sum(row["total_appointments"] for row in daily_counts)
    days_counted = len(daily_counts)
    global_average = total_all / days_counted if days_counted else 0

    # Если для конкретного дня недели нет никаких данных (0 в словаре),
    # можем для «красоты» подменять 0 на общее среднее:
    for dow in range(7):
        if day_of_week_avg[dow] == 0 and global_average != 0:
            day_of_week_avg[dow] = global_average

    # Формируем прогноз на будущее
    forecast_data = []
    for i in range(days_ahead):
        day = forecast_date + timedelta(days=i)
        dow = day.weekday()
        avg_value = day_of_week_avg.get(dow, global_average)
        forecast_data.append({
            "date": day.date().isoformat(),
            "forecast_appointments": round(avg_value)
        })

    return forecast_data
