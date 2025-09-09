# Copyright (c) 2024, Rifat Dzhumagulov and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today, getdate


class Carwash(Document):
	@frappe.whitelist()
	def has_journal_feature(self, feature_alias):
		"""
		Check if this car wash has a specific journal feature through its active subscription
		Results are cached for 3 minutes to improve performance
		
		Args:
			feature_alias (str): The alias of the journal feature to check
			
		Returns:
			bool: True if the feature exists in the active subscription, False otherwise
		"""
		try:
			print(f"DEBUG has_journal_feature: car_wash={self.name}, feature_alias={feature_alias}")
			
			# Create cache key based on car wash name and feature alias
			cache_key = f"car_wash_feature_{self.name}_{feature_alias}"
			
			# Try to get from cache first
			cached_result = frappe.cache().get_value(cache_key)
			if cached_result is not None:
				return cached_result
			
			# If not in cache, calculate the result
			result = self._check_journal_feature(feature_alias)
			print(f"DEBUG has_journal_feature result: {result}")
			
			# Cache the result for 3 minutes (180 seconds)
			frappe.cache().set_value(cache_key, result, expires_in_sec=180)
			
			return result
		except Exception as e:
			print(f"DEBUG has_journal_feature ERROR: {str(e)}")
			frappe.log_error(f"Error in has_journal_feature: {str(e)}", "Car Wash Feature Check Error")
			return False
	
	def _check_journal_feature(self, feature_alias):
		"""
		Internal method to check journal feature without caching
		"""
		print(f"DEBUG _check_journal_feature: car_wash={self.name}, feature_alias={feature_alias}")
		
		# Get active subscription for this car wash
		active_subscription = self.get_active_subscription()
		print(f"DEBUG _check_journal_feature active_subscription: {active_subscription}")
		
		if not active_subscription:
			print("DEBUG _check_journal_feature: No active subscription found")
			return False
		
		# Use the subscription's method to check for the feature
		result = active_subscription.has_journal_feature(feature_alias)
		print(f"DEBUG _check_journal_feature subscription result: {result}")
		return result
	
	def get_active_subscription(self):
		"""
		Get the active subscription for this car wash
		
		Returns:
			Car wash subscription document or None if no active subscription
		"""
		try:
			print(f"DEBUG get_active_subscription: car_wash={self.name}")
			
			# Create cache key for active subscription
			cache_key = f"car_wash_active_subscription_{self.name}"
			
			# Try to get from cache first
			cached_result = frappe.cache().get_value(cache_key)
			if cached_result is not None:
				if cached_result == "None":
					return None
				else:
					# Return the cached subscription document
					return frappe.get_doc("Car wash subscription", cached_result)
			
			# If not in cache, calculate the result
			subscription = None
			
			# Find active subscription for this car wash using SQL to handle date comparison
			from frappe.utils import today
			today_str = today()  # today() already returns a string in 'YYYY-MM-DD' format
			print(f"DEBUG get_active_subscription: today_str={today_str}")
			
			subscriptions = frappe.db.sql("""
				SELECT name 
				FROM `tabCar wash subscription`
				WHERE car_wash = %s 
				AND status = 'Active'
				AND starts_at <= %s
				AND (ends_at IS NULL OR ends_at >= %s)
				ORDER BY starts_at DESC
				LIMIT 1
			""", (self.name, today_str, today_str), as_dict=True)
			
			print(f"DEBUG get_active_subscription: SQL result={subscriptions}")
			
			if subscriptions:
				# Subscription is already validated as active by SQL query
				subscription = frappe.get_doc("Car wash subscription", subscriptions[0].name)
				print(f"DEBUG get_active_subscription: Found subscription={subscription.name}")
			else:
				print("DEBUG get_active_subscription: No active subscription found")
			
			# Cache the result for 3 minutes (180 seconds)
			frappe.cache().set_value(cache_key, subscription.name if subscription else "None", expires_in_sec=180)
			
			return subscription
		except Exception as e:
			print(f"DEBUG get_active_subscription ERROR: {str(e)}")
			frappe.log_error(f"Error in get_active_subscription: {str(e)}", "Car Wash Subscription Error")
			return None
	
	def get_journal_features(self):
		"""
		Get all journal features for this car wash through its active subscription
		Results are cached for 3 minutes to improve performance
		
		Returns:
			list: List of journal feature aliases
		"""
		# Create cache key for all features
		cache_key = f"car_wash_features_{self.name}"
		
		# Try to get from cache first
		cached_result = frappe.cache().get_value(cache_key)
		if cached_result is not None:
			return cached_result
		
		# If not in cache, calculate the result
		features = []
		active_subscription = self.get_active_subscription()
		
		if active_subscription:
			features = active_subscription.get_journal_features()
		
		# Cache the result for 3 minutes (180 seconds)
		frappe.cache().set_value(cache_key, features, expires_in_sec=180)
		
		return features
	
	def clear_feature_cache(self):
		"""
		Clear all cached feature data for this car wash
		Call this method when car wash or its subscription is updated
		"""
		# Clear individual feature checks
		cache_key = f"car_wash_feature_{self.name}_*"
		frappe.cache().delete_keys(cache_key)
		
		# Clear active subscription cache
		cache_key = f"car_wash_active_subscription_{self.name}"
		frappe.cache().delete_value(cache_key)
		
		# Clear all features cache
		cache_key = f"car_wash_features_{self.name}"
		frappe.cache().delete_value(cache_key)
	
	def on_update(self):
		"""
		Clear cache when car wash is updated
		"""
		self.clear_feature_cache()
