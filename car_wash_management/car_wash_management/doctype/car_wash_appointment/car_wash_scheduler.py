import frappe
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional


class CarWashScheduler:
	"""
	Считает свободные слоты:
	  - Нет рабочих часов -> 24/7
	  - Вместимость = число доступных боксов
	  - Записи (appointments) занимают слоты на время мойки (по умолчанию 45 минут)
	  - Очередь (Car wash booking):
		  * Каждая машина = 1 списание слота на время мойки
		  * Если есть desired_time (на строке или родителе), нельзя раньше него
	"""

	DOCTYPE_CAR_WASH = "Car wash"
	DOCTYPE_BOX = "Car wash box"  # Поставь None, если нет отдельного Doctype для боксов
	DOCTYPE_APPOINTMENT = "Car wash appointment"
	DOCTYPE_BOOKING = "Car wash booking"

	FIELD_WORKING_HOURS = "working_hours"  # child table: day_of_week, non_working, start_time, end_time
	FIELD_BOX_DISABLED = "is_disabled"
	FIELD_BOX_DELETED = "is_deleted"
	FIELD_APPT_START = "starts_on"
	FIELD_APPT_END = "ends_on"  # для справки
	FIELD_APPT_BOX = "box"
	# FIELD_APPT_DURATION = "duration_minutes"  # опциональное поле для длительности

	FIELD_BOOKING_DESIRED_TIME = "desired_time"  # опционально

	BOX_COUNT_FALLBACK = 1
	DEFAULT_WASH_DURATION_MINUTES = 45  # время мойки по умолчанию

	def __init__(self, car_wash_name: str, default_wash_duration: int = None):
		if not car_wash_name:
			raise ValueError("car_wash_name is required")
		self.car_wash_name = car_wash_name
		self.default_wash_duration = default_wash_duration or self.DEFAULT_WASH_DURATION_MINUTES

	# ---------- Public API ----------

	def get_free_slots_for_date(
		self,
		date_: datetime,
		step_minutes: int = 15,
		max_results: Optional[int] = None,
		include_capacity: bool = False,
		respect_queue: bool = True,
	) -> List[Dict]:
		try:
			from frappe.utils import now_datetime
			now = now_datetime()
		except Exception:
			now = datetime.now()

		day_start = datetime.combine(date_.date(), time(0, 0, 0))
		day_end = day_start + timedelta(days=1)

		if now.date() > date_.date():
			return []

		min_slot_start = day_start if date_.date() > now.date() else self._ceil_dt(
			max(now, day_start), step_minutes)
		if min_slot_start >= day_end:
			return []

		capacity_timeline = self._build_capacity_timeline(min_slot_start, day_end, step_minutes)

		appointments = self._get_appointments(min_slot_start, day_end)
		self._apply_appointments(capacity_timeline, appointments, step_minutes)

		if respect_queue:
			queue_items = self._get_queue_items(min_slot_start, day_end, step_minutes)
			self._apply_queue(capacity_timeline, queue_items, step_minutes)

		free = []
		for slot_start, capacity in capacity_timeline:
			if capacity > 0:
				slot_end = slot_start + timedelta(minutes=step_minutes)
				item = {
					"start": slot_start.strftime("%Y-%m-%d %H:%M:%S"),
					"end": slot_end.strftime("%Y-%m-%d %H:%M:%S"),
				}
				if include_capacity:
					item["capacity"] = capacity
				free.append(item)
				if max_results and len(free) >= max_results:
					break

		return free

	# ---------- Internals ----------

	def _build_capacity_timeline(self, start_dt: datetime, end_dt: datetime, step_minutes: int):
		boxes_count = self._get_boxes_count()
		intervals = self._get_working_dt_intervals_for_day(start_dt, end_dt)

		timeline = []
		cur = start_dt
		step = timedelta(minutes=step_minutes)
		while cur < end_dt:
			in_work = any(st <= cur < et for st, et in intervals)
			capacity = boxes_count if in_work else 0
			timeline.append((cur, capacity))
			cur += step
		return timeline

	def _get_working_dt_intervals_for_day(self, day_start: datetime, day_end: datetime) -> List[
		tuple]:
		car_wash = frappe.get_doc(self.DOCTYPE_CAR_WASH, self.car_wash_name)
		rows = getattr(car_wash, self.FIELD_WORKING_HOURS, None) or []

		if not rows:
			return [(day_start, day_end)]  # 24/7

		W = day_start.weekday()
		W_prev = (W - 1) % 7

		intervals: List[tuple] = []

		# текущий день
		for r in rows:
			if r.get("non_working"):
				continue
			if r.get("day_of_week") != W:
				continue
			st_t = r.get("start_time") or time(0, 0, 0)
			et_t = r.get("end_time") or time(23, 59, 59)

			if st_t <= et_t:
				intervals.append((
					day_start + timedelta(hours=st_t.hour, minutes=st_t.minute,
										  seconds=st_t.second),
					day_start + timedelta(hours=et_t.hour, minutes=et_t.minute,
										  seconds=et_t.second),
				))
			else:
				# через полночь: хвост до конца суток
				intervals.append((
					day_start + timedelta(hours=st_t.hour, minutes=st_t.minute,
										  seconds=st_t.second),
					day_end,
				))

		# хвост прошлого дня, если там интервал через полночь
		for r in rows:
			if r.get("non_working"):
				continue
			if r.get("day_of_week") != W_prev:
				continue
			st_t = r.get("start_time") or time(0, 0, 0)
			et_t = r.get("end_time") or time(23, 59, 59)
			if st_t > et_t:
				intervals.append((day_start,
								  day_start + timedelta(hours=et_t.hour, minutes=et_t.minute,
														seconds=et_t.second)))

		# merge
		intervals.sort(key=lambda x: x[0])
		merged: List[tuple] = []
		for st, et in intervals:
			if not merged or st > merged[-1][1]:
				merged.append((st, et))
			else:
				merged[-1] = (merged[-1][0], max(merged[-1][1], et))
		return merged

	def _get_boxes_count(self) -> int:
		# 1) нет Doctype боксов
		if not self.DOCTYPE_BOX:
			return self._boxes_from_car_wash_or_fallback()

		# 2) с Doctype боксов
		filters = {"car_wash": self.car_wash_name}
		try:
			meta = frappe.get_meta(self.DOCTYPE_BOX)
			fields = set(meta.get_fieldnames() or [])
			if self.FIELD_BOX_DISABLED in fields:
				filters[self.FIELD_BOX_DISABLED] = ["in", [0, False]]
			if self.FIELD_BOX_DELETED in fields:
				filters[self.FIELD_BOX_DELETED] = ["in", [0, False]]

			names = frappe.get_all(self.DOCTYPE_BOX, filters=filters, pluck="name")
			if names:
				return len(names)

			# повтор без опц. флагов
			names = frappe.get_all(self.DOCTYPE_BOX, filters={"car_wash": self.car_wash_name},
								   pluck="name")
			if names:
				return len(names)
		except Exception:
			pass

		return self._boxes_from_car_wash_or_fallback()

	def _boxes_from_car_wash_or_fallback(self) -> int:
		try:
			cw = frappe.get_doc(self.DOCTYPE_CAR_WASH, self.car_wash_name)
			if hasattr(cw, "boxes_count") and cw.boxes_count:
				return int(cw.boxes_count)
		except Exception:
			pass
		return self.BOX_COUNT_FALLBACK

	def _get_appointments(self, earliest_dt: datetime, day_end: datetime):
		return frappe.get_all(
			self.DOCTYPE_APPOINTMENT,
			filters=[
				["Car wash appointment", "car_wash", "=", self.car_wash_name],
				[self.FIELD_APPT_START, ">=", earliest_dt],
				[self.FIELD_APPT_START, "<", day_end],
			],
			fields=["name", self.FIELD_APPT_START, self.FIELD_APPT_END, self.FIELD_APPT_BOX],
			order_by=f"{self.FIELD_APPT_START} asc",
		)

	# ---- NEW: robust queue expand ----
	def _get_queue_items(self, min_slot_start: datetime, day_end: datetime, step_minutes: int):
		"""
		Возвращает список элементов очереди вида:
		  { "earliest_dt": datetime }
		1 бронь = 1 машина (т.к. в твоём Doctype нет отдельной child-таблицы машин).
		Берём только активные брони без назначенного апоинтмента.
		"""
		# Найдём реальное линк-поле на Car wash в Booking
		booking_filters = self._booking_filters_for_car_wash()
		# Добавим статусы/флаги
		booking_filters.update({
			"is_deleted": ["in", [0, False]],
			"is_cancelled": ["in", [0, False]],
			"has_appointment": ["in", [0, False]],
		})

		bookings = frappe.get_all(
			self.DOCTYPE_BOOKING,
			filters=booking_filters,
			fields=["name", self.FIELD_BOOKING_DESIRED_TIME, "creation"],
			order_by=f"{self.FIELD_BOOKING_DESIRED_TIME} asc, creation asc",
			limit_page_length=1000,
		)

		items = []
		for b in bookings:
			desired = b.get(self.FIELD_BOOKING_DESIRED_TIME)
			# не раньше желаемого/минимального старта и в сетку слотов
			earliest = desired if isinstance(desired,
											 datetime) and desired > min_slot_start else min_slot_start
			earliest = self._ceil_dt(earliest, step_minutes)
			if earliest < day_end:
				items.append({"earliest_dt": earliest})
		# Самая ранняя подача — в приоритете
		items.sort(key=lambda x: x["earliest_dt"])
		return items

	def _booking_filters_for_car_wash(self) -> Dict[str, str]:
		"""
		Находим реальное линк-поле на Car wash внутри DOCTYPE_BOOKING.
		Если не нашли — используем 'car_wash'.
		"""
		try:
			meta = frappe.get_meta(self.DOCTYPE_BOOKING)
			for f in meta.fields:
				if getattr(f, "fieldtype", "") == "Link" and getattr(f, "options",
																	 "") == self.DOCTYPE_CAR_WASH:
					return {f.fieldname: self.car_wash_name}
		except Exception:
			pass
		return {"car_wash": self.car_wash_name}

	def _apply_appointments(self, timeline, appointments, step_minutes: int):
		"""
		Применяет записи к таймлайну. Каждая запись блокирует слоты на время мойки.
		"""
		for appt in appointments:
			ap_s = appt.get(self.FIELD_APPT_START)
			if not isinstance(ap_s, datetime):
				continue

			# Определяем длительность мойки
			duration = self.default_wash_duration

			# Находим начальный слот
			slot_start = self._floor_dt(ap_s, step_minutes)

			# Блокируем все слоты на время мойки
			current_time = slot_start
			end_time = ap_s + timedelta(minutes=duration)

			while current_time < end_time:
				idx = self._find_slot_index(timeline, current_time,
											timedelta(minutes=step_minutes))
				if idx < len(timeline) and timeline[idx][0] == current_time:
					slot_time, cap = timeline[idx]
					timeline[idx] = (slot_time, max(0, cap - 1))
				current_time += timedelta(minutes=step_minutes)

	def _apply_queue(self, timeline, queue_items, step_minutes: int):
		"""
		Применяет очередь к таймлайну. Каждый элемент очереди ищет первое свободное время
		и блокирует слоты на время мойки.
		"""
		queue_items.sort(key=lambda x: x["earliest_dt"])

		for q in queue_items:
			earliest = q["earliest_dt"]

			# Ищем первый доступный слот начиная с earliest
			idx = self._find_slot_index(timeline, earliest, timedelta(minutes=step_minutes))

			# Проверяем, хватает ли места для полной мойки
			while idx < len(timeline):
				slot_start, cap = timeline[idx]

				if cap > 0:
					# Проверяем, можно ли разместить полную мойку начиная с этого слота
					if self._can_place_wash_at_slot(timeline, idx, step_minutes):
						# Размещаем мойку
						self._place_wash_at_slot(timeline, idx, step_minutes)
						break

				idx += 1

	def _can_place_wash_at_slot(self, timeline, start_idx: int, step_minutes: int) -> bool:
		"""
		Проверяет, можно ли разместить мойку начиная с указанного слота.
		"""
		wash_slots_needed = (self.default_wash_duration + step_minutes - 1) // step_minutes

		for i in range(wash_slots_needed):
			slot_idx = start_idx + i
			if slot_idx >= len(timeline):
				return False
			if timeline[slot_idx][1] <= 0:  # нет свободной емкости
				return False

		return True

	def _place_wash_at_slot(self, timeline, start_idx: int, step_minutes: int):
		"""
		Размещает мойку начиная с указанного слота.
		"""
		wash_slots_needed = (self.default_wash_duration + step_minutes - 1) // step_minutes

		for i in range(wash_slots_needed):
			slot_idx = start_idx + i
			if slot_idx < len(timeline):
				slot_time, cap = timeline[slot_idx]
				timeline[slot_idx] = (slot_time, max(0, cap - 1))

	# ---------- Helpers ----------

	@staticmethod
	def _find_slot_index(timeline, when: datetime, step: timedelta) -> int:
		if not timeline:
			return 0
		if when <= timeline[0][0]:
			return 0
		for i, (slot_start, _) in enumerate(timeline):
			if slot_start >= when:
				return i
		return len(timeline)

	@staticmethod
	def _ceil_dt(dt_: datetime, step_minutes: int) -> datetime:
		base = datetime.combine(dt_.date(), time(0, 0))
		step = timedelta(minutes=step_minutes)
		delta = (dt_ - base)
		secs = int(delta.total_seconds())
		step_secs = int(step.total_seconds())
		k = (secs + step_secs - 1) // step_secs
		return base + timedelta(seconds=k * step_secs)

	@staticmethod
	def _floor_dt(dt_: datetime, step_minutes: int) -> datetime:
		base = datetime.combine(dt_.date(), time(0, 0))
		step = timedelta(minutes=step_minutes)
		delta = (dt_ - base)
		secs = int(delta.total_seconds())
		step_secs = int(step.total_seconds())
		k = secs // step_secs
		return base + timedelta(seconds=k * step_secs)
