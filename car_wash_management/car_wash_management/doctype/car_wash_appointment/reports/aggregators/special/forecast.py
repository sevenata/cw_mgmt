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
from typing import Any, Dict, List, Tuple
import datetime as _dt
import frappe
from ...base import MetricAggregator, ReportContext


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

        # Следующая неделя (даты)
        next_week_start = context.current_week.end
        forecast: List[Dict[str, Any]] = []
        for i in range(7):
            day = next_week_start + _dt.timedelta(days=i)
            wd = day.weekday()
            value = preliminary_forecast_by_wd.get(wd, 0.0) * scale
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


