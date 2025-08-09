import frappe
from datetime import datetime, timedelta


class CarWashAppointmentManager:
	def __init__(self, car_wash_name=None):
		self.car_wash_name = car_wash_name

	def get_working_hours(self):
		if not self.car_wash_name:
			raise ValueError("Car wash name must be provided to fetch working hours.")

		car_wash = frappe.get_doc('Car wash', self.car_wash_name)
		working_hours_mapped = []

		for entry in car_wash.working_hours:
			hours = {
				'day_of_week': entry.get('day_of_week'),
				'non_working': entry.get('non_working'),
				'start_time': entry.get('start_time'),
				'end_time': entry.get('end_time'),
			}
			working_hours_mapped.append(hours)

		return working_hours_mapped

	def get_appointments(self, box_name=None, worker_name=None, car_name=None):
		filters = {}

		if self.car_wash_name:
			filters['car_wash'] = self.car_wash_name
		if box_name:
			filters['box'] = box_name
		if worker_name:
			filters['worker'] = worker_name
		if car_name:
			filters['car'] = car_name

		appointments = frappe.get_list('Car wash appointment',
									   fields=['name', 'starts_on', 'ends_on', 'worker', 'car'],
									   order_by='starts_on asc',
									   limit=5,
									   filters=filters)
		return appointments

	def get_time_intervals(self, day_of_week):
		schedules = self.get_working_hours()
		day_schedule = next((s for s in schedules if s['day_of_week'] == day_of_week), None)

		if not day_schedule or day_schedule['non_working']:
			return []

		start_time = day_schedule['start_time']
		end_time = day_schedule['end_time']

		base_time = datetime.combine(datetime.today(), datetime.min.time())
		time_intervals = []

		current_time = base_time + start_time
		end_time = base_time + end_time

		while current_time <= end_time:
			time_intervals.append(current_time.strftime('%H:%M:%S'))
			current_time += timedelta(hours=1)

		return time_intervals

	def get_free_slots(self, box_name=None, worker_name=None):
		working_hours_list = self.get_working_hours()

		if not working_hours_list:
			return []

		working_hours = working_hours_list[0]
		start_of_day = datetime.combine(datetime.today(), datetime.min.time()) + working_hours[
			'start_time']
		end_of_day = datetime.combine(datetime.today(), datetime.min.time()) + working_hours[
			'end_time']

		appointments = self.get_appointments(box_name=box_name, worker_name=worker_name)
		free_slots = []
		current_time = start_of_day

		while current_time < end_of_day:
			next_time = current_time + timedelta(minutes=15)
			is_free = True

			for appointment in appointments:
				appointment_start = appointment['starts_on']
				appointment_end = appointment_start + timedelta(hours=1)

				if not (next_time <= appointment_start or current_time >= appointment_end):
					is_free = False
					break

			if is_free:
				free_slots.append({
					'start': current_time.strftime('%Y-%m-%d %H:%M:%S'),
					'end': next_time.strftime('%Y-%m-%d %H:%M:%S')
				})

			current_time = next_time

		return free_slots
