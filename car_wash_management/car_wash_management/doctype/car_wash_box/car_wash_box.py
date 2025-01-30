# Copyright (c) 2024, Rifat Dzhumagulov and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
from datetime import datetime, timedelta
from frappe import _

import frappe

from ..car_wash_booking.car_wash_booking import update_or_create_availability


class Carwashbox(Document):

	def validate(self):
		update_or_create_availability(self)

	def get_working_hours(self):
		car_wash = frappe.get_doc('Car wash', self.car_wash)
		# Initialize an empty list to store the mapped working hours
		working_hours_mapped = []

		# Assuming `working_hours` is a list of dictionaries
		for entry in car_wash.working_hours:
			# Map the required fields
			hours = {
				'day_of_week': entry.get('day_of_week'),
				'non_working': entry.get('non_working'),
				'start_time': entry.get('start_time'),
				'end_time': entry.get('end_time'),
			}
			# Add the mapped entry to the list
			working_hours_mapped.append(hours)

		return working_hours_mapped

	def get_time_intervals(self):
		schedules = self.get_working_hours()
		day_schedule = schedules[0]

		start_time = day_schedule['start_time']  # This is a timedelta
		end_time = day_schedule['end_time']  # This is a timedelta

		# Base time to start from (e.g., midnight)
		base_time = datetime.combine(datetime.today(), datetime.min.time())

		# Initialize a list to store the time intervals
		time_intervals = []

		# Create intervals by adding 1 hour to start_time until it reaches end_time
		current_time = base_time + start_time
		end_time = base_time + end_time

		while current_time <= end_time:
			time_intervals.append(current_time.strftime('%H:%M:%S'))
			current_time += timedelta(hours=1)

		return time_intervals

	def get_appointments(self):
		appointments = frappe.get_list('Car wash appointment', fields=['name', 'starts_on'],
									   order_by='starts_on asc', filters={
				'box': self.name
			})
		return appointments

	def get_free_slots(self):
		working_hours_list = self.get_working_hours()

		# Assuming you want the first working hours set
		working_hours = working_hours_list[0]

		start_of_day = datetime.combine(datetime.today(), datetime.min.time()) + working_hours[
			'start_time']
		end_of_day = datetime.combine(datetime.today(), datetime.min.time()) + working_hours[
			'end_time']

		appointments = self.get_appointments()

		free_slots = []
		current_time = start_of_day

		while current_time < end_of_day:
			next_time = current_time + timedelta(hours=1)
			# Check if the current time slot overlaps with any existing appointment
			is_free = True
			for appointment in appointments:
				appointment_start = appointment['starts_on']  # This is already a datetime object
				appointment_end = appointment_start + timedelta(
					hours=1)  # Assuming each appointment is 1 hour long

				if not (next_time <= appointment_start or current_time >= appointment_end):
					is_free = False
					break

			# If the time slot is free, add it to the list of free slots
			if is_free:
				free_slots.append({
					'start': current_time.strftime('%Y-%m-%d %H:%M:%S'),
					'end': next_time.strftime('%Y-%m-%d %H:%M:%S')
				})

			current_time = next_time

		return free_slots
