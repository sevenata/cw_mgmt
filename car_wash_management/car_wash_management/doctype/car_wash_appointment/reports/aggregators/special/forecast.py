"""Прогноз загрузки на следующую неделю.

Алгоритм (улучшенный):
- История: берем последние N недель (по умолчанию 16), исключая текущую.
- По каждой неделе строим профиль по дням недели (0..6).
- Выполняем робастное отсечение выбросов на уровне недельных рядов по дню недели
  с помощью медианы и MAD (winsorize по интервалу m ± k * 1.4826 * MAD).
- Сглаживаем ряды по дням недели экспоненциальным сглаживанием (EWMA),
  повышая вес недавних недель.
- Оцениваем недельный тренд как EWMA от коэффициентов роста totals[t]/totals[t-1].
- Формируем прогноз на следующую неделю: базовые DOW-значения * тренд,
  затем масштабируем так, чтобы сумма по дням соответствовала недельному прогнозу.
"""

from collections import defaultdict
from statistics import median
from typing import Any, Dict, List
import datetime as _dt
import frappe
from ...base import MetricAggregator, ReportContext
from car_wash_management import api as cw_api


class ForecastAggregator(MetricAggregator):
    HISTORY_WEEKS: int = 16
    EWMA_ALPHA_DOW: float = 0.3  # сглаживание профилей по дням недели
    EWMA_ALPHA_TREND: float = 0.3  # сглаживание недельного тренда (отношений)
    MAD_CLIP_K: float = 3.0  # ширина окна клиппинга по MAD

    def aggregate(self, data: List[Dict[str, Any]], context: ReportContext) -> List[Dict[str, Any]]:
        # История до начала текущей недели
        start = context.current_week.start - _dt.timedelta(days=7 * self.HISTORY_WEEKS)
        end = context.current_week.start

        rows = frappe.get_all(
            "Car wash appointment",
            fields=["starts_on"],
            filters={
                "car_wash": context.car_wash,
                "is_deleted": 0,
                "starts_on": ["between", [start, end]],
            },
            order_by="starts_on asc",
            limit=50000,
        )

        if not rows:
            return self._empty_next_week(context)

        # Подсчет по неделям и по дням недели
        # week_key = дата понедельника недели
        week_to_dow_counts: Dict[_dt.date, List[int]] = defaultdict(lambda: [0] * 7)
        for r in rows:
            d = frappe.utils.get_datetime(r["starts_on"]).date()
            week_start = d - _dt.timedelta(days=d.weekday())
            week_to_dow_counts[week_start][d.weekday()] += 1

        if not week_to_dow_counts:
            return self._empty_next_week(context)

        # Сортируем недели по времени (по возрастанию)
        sorted_weeks = sorted(week_to_dow_counts.keys())

        # Формируем ряды по каждому дню недели
        dow_series: Dict[int, List[float]] = {wd: [] for wd in range(7)}
        weekly_totals: List[float] = []
        for w in sorted_weeks:
            counts = week_to_dow_counts[w]
            weekly_totals.append(float(sum(counts)))
            for wd in range(7):
                dow_series[wd].append(float(counts[wd]))

        # Робастное отсечение выбросов для каждого ряда по дню недели
        for wd in range(7):
            dow_series[wd] = self._winsorize_by_mad(dow_series[wd], self.MAD_CLIP_K)

        # Пересчитываем totals после клиппинга (чтобы тренд был устойчивее)
        weekly_totals = [sum(dow_series[wd][i] for wd in range(7)) for i in range(len(sorted_weeks))]

        # EWMA по каждому дню недели → базовое значение на следующую неделю
        base_dow: Dict[int, float] = {}
        for wd in range(7):
            base_dow[wd] = self._ewma_last(dow_series[wd], self.EWMA_ALPHA_DOW)

        # EWMA тренд на уровне недельных totals через отношение соседних недель
        trend_multiplier = self._weekly_trend_multiplier(weekly_totals, self.EWMA_ALPHA_TREND)

        # Прогноз по дням до масштабирования
        preliminary_forecast_by_wd = {wd: max(0.0, base_dow.get(wd, 0.0) * trend_multiplier) for wd in range(7)}

        # Масштабирование, чтобы сумма по дням совпала с недельным прогнозом (last_total * trend)
        last_total = weekly_totals[-1] if weekly_totals else 0.0
        target_week_total = max(0.0, last_total * trend_multiplier)
        sum_prelim = sum(preliminary_forecast_by_wd.values())
        scale = (target_week_total / sum_prelim) if sum_prelim > 0 else 1.0

        # Погодные корректировки: рассчитываем коэффициенты по дням следующей недели
        next_week_start = context.current_week.end
        next_week_end = next_week_start + _dt.timedelta(days=7)
        weather_by_date = self._summarize_upcoming_weather(next_week_start, next_week_end)

        # Предварительно применим погодные факторы к значениям по дням недели
        factors_by_wd: Dict[int, float] = {}
        factors_list: List[float] = []
        for i in range(7):
            day = next_week_start + _dt.timedelta(days=i)
            day_iso = day.date().isoformat()
            weather = weather_by_date.get(day_iso)
            factor = self._weather_adjustment_factor(weather)
            factors_by_wd[day.weekday()] = factor
            factors_list.append(factor)

        factored_prelim_by_wd: Dict[int, float] = {}
        for wd, base_val in preliminary_forecast_by_wd.items():
            factored_prelim_by_wd[wd] = max(0.0, base_val * factors_by_wd.get(wd, 1.0))

        # Масштабирование для сохранения недельной логики с учетом средней погоды
        avg_factor = sum(factors_list) / 7.0 if factors_list else 1.0
        last_total = weekly_totals[-1] if weekly_totals else 0.0
        target_week_total = max(0.0, last_total * trend_multiplier * avg_factor)
        sum_prelim = sum(factored_prelim_by_wd.values())
        scale = (target_week_total / sum_prelim) if sum_prelim > 0 else 1.0

        # Следующая неделя (даты) с применением погодных факторов
        forecast: List[Dict[str, Any]] = []
        for i in range(7):
            day = next_week_start + _dt.timedelta(days=i)
            wd = day.weekday()
            value = factored_prelim_by_wd.get(wd, 0.0) * scale
            forecast.append({
                "date": day.isoformat(),
                "visits_forecast": round(value, 2),
            })
        return forecast

    def get_section_name(self) -> str:
        return "forecast"

    # ---------------------------
    # Вспомогательные методы
    # ---------------------------

    def _empty_next_week(self, context: ReportContext) -> List[Dict[str, Any]]:
        next_week_start = context.current_week.end
        result: List[Dict[str, Any]] = []
        for i in range(7):
            day = next_week_start + _dt.timedelta(days=i)
            result.append({"date": day.isoformat(), "visits_forecast": 0.0})
        return result

    def _ewma_last(self, sequence: List[float], alpha: float) -> float:
        if not sequence:
            return 0.0
        value = sequence[0]
        for x in sequence[1:]:
            value = alpha * x + (1.0 - alpha) * value
        return value

    def _winsorize_by_mad(self, sequence: List[float], k: float) -> List[float]:
        if not sequence:
            return []
        m = median(sequence)
        deviations = [abs(x - m) for x in sequence]
        mad = median(deviations) if deviations else 0.0
        if mad == 0.0:
            # Если нет разброса, возвращаем как есть
            return sequence[:]
        scale = 1.4826 * mad  # константа для приближения к std
        lower = m - k * scale
        upper = m + k * scale
        return [min(max(x, lower), upper) for x in sequence]

    def _weekly_trend_multiplier(self, weekly_totals: List[float], alpha: float) -> float:
        # Рассчитываем отношения соседних недель: r_t = total_t / total_{t-1}
        ratios: List[float] = []
        for i in range(1, len(weekly_totals)):
            prev = weekly_totals[i - 1]
            curr = weekly_totals[i]
            if prev > 0:
                ratios.append(curr / prev)
        if not ratios:
            return 1.0
        return max(0.0, self._ewma_last(ratios, alpha))

    # ---------------------------
    # Погода: загрузка и факторы
    # ---------------------------

    def _summarize_upcoming_weather(self, start_dt: _dt.datetime, end_dt: _dt.datetime) -> Dict[str, Dict[str, float]]:
        """Возвращает суточные сводки погоды по датам ISO в интервале [start_dt, end_dt).
        Поля: temp_min, temp_max, precip_mm, snow_mm, gust_ms.
        """
        cache_key = f"weather_forecast_astana"
        cached = frappe.cache().get_value(cache_key)
        raw = None
        if cached:
            try:
                raw = frappe.parse_json(cached)
            except Exception:
                raw = None
        if raw is None:
            try:
                raw = cw_api.get_weather()  # dict c ключами, как у OpenWeatherMap 5-day/3h
                # кэшируем на 6 часов
                try:
                    frappe.cache().set_value(cache_key, raw, expires_in_sec=6 * 60 * 60)
                except Exception:
                    pass
            except Exception:
                raw = None
        if not isinstance(raw, dict):
            return {}

        buckets: Dict[str, Dict[str, Any]] = {}
        for it in raw.get("list", []) or []:
            dt_txt = it.get("dt_txt")
            if not dt_txt:
                continue
            try:
                dt = frappe.utils.get_datetime(dt_txt)
            except Exception:
                continue
            if not (start_dt <= dt < end_dt):
                continue
            day_iso = dt.date().isoformat()
            b = buckets.setdefault(day_iso, {"temps": [], "gusts": [], "precip": 0.0, "snow": 0.0})
            main = it.get("main") or {}
            wind = it.get("wind") or {}
            if isinstance(main.get("temp"), (int, float)):
                b["temps"].append(float(main["temp"]))
            gust = wind.get("gust")
            if isinstance(gust, (int, float)):
                b["gusts"].append(float(gust))  # m/s в metric
            rain3h = 0.0
            snow3h = 0.0
            try:
                if isinstance(it.get("rain", {}).get("3h"), (int, float)):
                    rain3h = float(it["rain"]["3h"])
            except Exception:
                pass
            try:
                if isinstance(it.get("snow", {}).get("3h"), (int, float)):
                    snow3h = float(it["snow"]["3h"])
            except Exception:
                pass
            b["precip"] += rain3h
            b["snow"] += snow3h

        result: Dict[str, Dict[str, float]] = {}
        for day_iso, b in buckets.items():
            temps: List[float] = b["temps"]
            gusts: List[float] = b["gusts"]
            temp_min = min(temps) if temps else None
            temp_max = max(temps) if temps else None
            gust_ms = max(gusts) if gusts else None
            result[day_iso] = {
                "temp_min": float(temp_min) if temp_min is not None else 0.0,
                "temp_max": float(temp_max) if temp_max is not None else 0.0,
                "precip_mm": round(float(b["precip"]), 2),
                "snow_mm": round(float(b["snow"]), 2),
                "gust_ms": float(gust_ms) if gust_ms is not None else 0.0,
            }
        return result

    def _weather_adjustment_factor(self, dw: Dict[str, float] | None) -> float:
        """Эвристический множитель по погоде.
        Учитываем осадки (дождь/снег), порывы ветра и экстремальные температуры.
        """
        if not dw:
            return 1.0
        precip = float(dw.get("precip_mm", 0.0))
        snow = float(dw.get("snow_mm", 0.0))
        gust = float(dw.get("gust_ms", 0.0))
        tmin = float(dw.get("temp_min", 0.0))
        tmax = float(dw.get("temp_max", 0.0))

        factor = 1.0
        # Осадки: 3% снижения за мм дождя (до 30%), снег в 2x сильнее.
        wet_index = precip + 2.0 * snow
        if wet_index > 0:
            factor *= max(0.7, 1.0 - 0.03 * wet_index)

        # Ветер: после 10 м/с уменьшаем 1% за м/с, до 15%
        if gust > 10.0:
            factor *= max(0.85, 1.0 - 0.01 * (gust - 10.0))

        # Температура: сильный мороз/жара влияют
        if tmax < -20.0:
            factor *= 0.8
        elif tmax < -10.0:
            factor *= 0.9
        elif tmax > 35.0:
            factor *= 0.9

        # Ограничим диапазон факторов
        return max(0.5, min(1.1, factor))


