import frappe
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional


class CarWashScheduler:
    """
    Computes free time slots for a car wash with:
      - Working hours (if missing => 24/7)
      - Boxes capacity (number of boxes)
      - Existing appointments (with starts_on/ends_on)
      - Queue from `Car wash booking` (no box/worker assigned):
          * Each car in the queue reserves the earliest feasible free slot.
          * If booking.desired_time is set – it can't be scheduled before that.
    """

    # ---- Adjust these if your DocType names/fields differ ----
    DOCTYPE_CAR_WASH = "Car wash"
    DOCTYPE_BOX = "Car wash box"                 # Set to None if you don't have a boxes doctype
    DOCTYPE_APPOINTMENT = "Car wash appointment"
    DOCTYPE_BOOKING = "Car wash booking"

    FIELD_WORKING_HOURS = "working_hours"        # child table on Car wash with day_of_week, non_working, start_time, end_time
    FIELD_BOX_DISABLED = "is_disabled"
    FIELD_BOX_DELETED = "is_deleted"
    FIELD_APPT_START = "starts_on"
    FIELD_APPT_END = "ends_on"
    FIELD_APPT_BOX = "box"

    FIELD_BOOKING_DESIRED_TIME = "desired_time"  # optional field on Car wash booking

    # If you don't have a boxes table, use this fallback:
    BOX_COUNT_FALLBACK = 1

    def __init__(self, car_wash_name: str):
        if not car_wash_name:
            raise ValueError("car_wash_name is required")
        self.car_wash_name = car_wash_name

    # ---------- Public API ----------

    def get_free_slots_for_date(
        self,
        date_: datetime,
        step_minutes: int = 15,
        max_results: Optional[int] = None,
        include_capacity: bool = False,
        respect_queue: bool = True,
    ) -> List[Dict]:
        """
        Returns available slots (after subtracting appointments and queue).
        Each item: {start: str, end: str} or also {capacity:int} if include_capacity.

        Args:
            date_: a datetime (date part used; local system time zone assumed).
            step_minutes: granularity for slots.
            max_results: truncate results to this count (None = all).
            include_capacity: return remaining per-slot capacity.
            respect_queue: consume capacity by queued cars (with desired_time respected).
        """
        day_start = datetime.combine(date_.date(), time(0, 0, 0))
        day_end = day_start + timedelta(days=1)

        print(day_start)
        print(day_end)

        # 1) Capacity over the day according to working hours and boxes
        capacity_timeline = self._build_capacity_timeline(day_start, day_end, step_minutes)

        # 2) Subtract existing appointments
        appointments = self._get_appointments(day_start, day_end)
        self._apply_appointments(capacity_timeline, appointments, step_minutes)

        print(appointments)

        # 3) Subtract queued cars (each car consumes 1 slot)
        if respect_queue:
            queue_items = self._get_queue_items(day_start, day_end)
            self._apply_queue(capacity_timeline, queue_items, step_minutes)

        # 4) Collect remaining free slots
        free = []
        print(capacity_timeline)
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
        """Create [(slot_start_dt, capacity_int), ...] for the day based on working hours & boxes."""
        boxes_count = self._get_boxes_count()

        # Working intervals for this specific weekday
        weekday = start_dt.weekday()  # Monday=0 ... Sunday=6
        intervals = self._get_working_intervals_for_weekday(weekday)

        # If 24/7, intervals is full day [00:00, 24:00)
        timeline = []
        cur = start_dt
        step = timedelta(minutes=step_minutes)
        while cur < end_dt:
            in_work = self._dt_in_any_interval(cur, intervals)
            capacity = boxes_count if in_work else 0
            timeline.append((cur, capacity))
            cur += step
        return timeline

    def _get_working_intervals_for_weekday(self, weekday: int):
        """
        Returns a list of (start_t: time, end_t: time) for the weekday.
        If no working hours defined at all -> 24/7.
        If a day's entry is non_working -> empty list.
        """
        car_wash = frappe.get_doc(self.DOCTYPE_CAR_WASH, self.car_wash_name)
        rows = getattr(car_wash, self.FIELD_WORKING_HOURS, None) or []

        if not rows:
            # 24/7 for all days
            return [(time(0, 0, 0), time(23, 59, 59))]

        day_rows = []
        for r in rows:
            # Expect r.day_of_week as 0-6; if string, map as needed
            row_weekday = r.get("day_of_week")
            if row_weekday == weekday and not r.get("non_working"):
                st = r.get("start_time") or time(0, 0, 0)
                et = r.get("end_time") or time(23, 59, 59)
                day_rows.append((st, et))

        return day_rows

    def _get_boxes_count(self) -> int:
        """Return number of enabled boxes; if no boxes doc, fallback to BOX_COUNT_FALLBACK."""
        if not self.DOCTYPE_BOX:
            return self.BOX_COUNT_FALLBACK

        boxes = frappe.get_all(
            self.DOCTYPE_BOX,
            filters={"car_wash": self.car_wash_name, self.FIELD_BOX_DISABLED: 0, self.FIELD_BOX_DELETED: 0},
            pluck="name",
        )
        return len(boxes) if boxes else self.BOX_COUNT_FALLBACK

    def _get_appointments(self, start_dt: datetime, end_dt: datetime):
        """All appointments overlapping [start_dt, end_dt)."""
        # Fetch appointments for this car wash overlapping the day
        # (starts_on < end_dt) and (ends_on > start_dt)
        return frappe.get_all(
            self.DOCTYPE_APPOINTMENT,
            filters={
                "car_wash": self.car_wash_name,
                self.FIELD_APPT_START: ("<", end_dt),
                self.FIELD_APPT_END: (">", start_dt),
            },
            fields=["name", self.FIELD_APPT_START, self.FIELD_APPT_END, self.FIELD_APPT_BOX],
            order_by=f"{self.FIELD_APPT_START} asc",
        )

    def _get_queue_items(self, day_start: datetime, day_end: datetime):
        """
        Produce 1 item per car in the queue:
            { earliest_dt: datetime }
        If booking.desired_time is set and >= day_start – use it; otherwise use day_start.
        If you store multiple cars per booking, either:
          - duplicate the booking in your query (one per car), or
          - extend this function to read the child table and emit N items.
        """
        # Basic approach assumes 1 car per booking. If you have many cars per booking,
        # fetch the child rows and expand them to multiple items.
        filters = {"car_wash": self.car_wash_name}

        bookings = frappe.get_all(
            self.DOCTYPE_BOOKING,
            filters=filters,
            fields=["name", self.FIELD_BOOKING_DESIRED_TIME, "creation"],
            order_by=f"{self.FIELD_BOOKING_DESIRED_TIME} asc, creation asc",
        )

        items = []
        for b in bookings:
            desired = b.get(self.FIELD_BOOKING_DESIRED_TIME)
            earliest = None
            if desired and isinstance(desired, datetime):
                earliest = desired if desired >= day_start else day_start
            else:
                earliest = day_start
            items.append({"earliest_dt": earliest})
            # If you have child rows with multiple cars, append more items here.

        return items

    def _apply_appointments(self, timeline, appointments, step_minutes: int):
        """Decrease capacity for every slot overlapped by an appointment (1 box per appointment)."""
        step = timedelta(minutes=step_minutes)
        for appt in appointments:
            ap_s = appt[self.FIELD_APPT_START]
            ap_e = appt[self.FIELD_APPT_END]
            if not isinstance(ap_s, datetime) or not isinstance(ap_e, datetime):
                continue
            for i, (slot_start, cap) in enumerate(timeline):
                slot_end = slot_start + step
                if self._overlaps(slot_start, slot_end, ap_s, ap_e):
                    timeline[i] = (slot_start, max(0, cap - 1))

    def _apply_queue(self, timeline, queue_items, step_minutes: int):
        """
        Greedy assignment: for each queued car, find the earliest slot
        at/after earliest_dt with capacity>0 and subtract 1.
        """
        step = timedelta(minutes=step_minutes)
        # Sort by earliest_dt
        queue_items.sort(key=lambda x: x["earliest_dt"])

        for q in queue_items:
            earliest = q["earliest_dt"]
            # Find index of first slot >= earliest
            idx = self._find_slot_index(timeline, earliest, step)
            while idx < len(timeline):
                slot_start, cap = timeline[idx]
                if cap > 0:
                    timeline[idx] = (slot_start, cap - 1)
                    break
                idx += 1

    # ---------- Helpers ----------

    @staticmethod
    def _overlaps(a_s, a_e, b_s, b_e) -> bool:
        return not (a_e <= b_s or a_s >= b_e)

    @staticmethod
    def _dt_in_any_interval(dt: datetime, intervals: List[tuple]) -> bool:
        t = dt.time()
        for st, et in intervals:
            if st <= t <= et:
                return True
        return False

    @staticmethod
    def _find_slot_index(timeline, when: datetime, step: timedelta) -> int:
        if when <= timeline[0][0]:
            return 0
        # linear scan is fine for daily grid; if you expand to multi-day, switch to bisect
        for i, (slot_start, _) in enumerate(timeline):
            if slot_start >= when:
                return i
        return len(timeline)
