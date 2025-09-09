# Copyright (c) 2025, Rifat and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cint


class Carwashsubscription(Document):
	@frappe.whitelist()
	def has_journal_feature(self, feature_alias):
		"""
		Check if this car wash subscription has a specific journal feature
		Results are cached for 3 minutes to improve performance
		
		Args:
			feature_alias (str): The alias of the journal feature to check
			
		Returns:
			bool: True if the feature exists in the subscription, False otherwise
		"""
		try:
			print(f"DEBUG subscription has_journal_feature: subscription={self.name}, feature_alias={feature_alias}")
			
			# Create cache key based on subscription name and feature alias
			cache_key = f"subscription_feature_{self.name}_{feature_alias}"
			
			# Try to get from cache first
			cached_result = frappe.cache().get_value(cache_key)
			if cached_result is not None:
				print(f"DEBUG subscription has_journal_feature: Found in cache={cached_result}")
				return cint(cached_result)
			
			# If not in cache, calculate the result
			result = self._check_journal_feature(feature_alias)
			print(f"DEBUG subscription has_journal_feature: Calculated result={result}")
			
			# Cache the result for 3 minutes (180 seconds)
			frappe.cache().set_value(cache_key, result, expires_in_sec=180)
			
			return result
		except Exception as e:
			print(f"DEBUG subscription has_journal_feature ERROR: {str(e)}")
			frappe.log_error(f"Error in subscription has_journal_feature: {str(e)}", "Subscription Feature Check Error")
			return False
	
	def _check_journal_feature(self, feature_alias):
		"""
		Internal method to check journal feature without caching
		"""
		print(f"DEBUG subscription _check_journal_feature: subscription={self.name}, feature_alias={feature_alias}")
		print(f"DEBUG subscription _check_journal_feature: features={self.features}")
		
		if not self.features:
			print("DEBUG subscription _check_journal_feature: No features found")
			return False
			
		for feature_row in self.features:
			print(f"DEBUG subscription _check_journal_feature: Checking feature_row={feature_row}")
			if feature_row.feature:
				# Get the journal feature document to check its alias
				try:
					journal_feature = frappe.get_doc("Car wash journal feature", feature_row.feature)
					print(f"DEBUG subscription _check_journal_feature: journal_feature={journal_feature.alias}")
					if journal_feature.alias == feature_alias:
						print("DEBUG subscription _check_journal_feature: MATCH FOUND!")
						return True
				except Exception as e:
					print(f"DEBUG subscription _check_journal_feature: Error getting journal feature {feature_row.feature}: {str(e)}")
		
		print("DEBUG subscription _check_journal_feature: No match found")
		return False
	
	def get_journal_features(self):
		"""
		Get all journal features for this subscription
		Results are cached for 3 minutes to improve performance
		
		Returns:
			list: List of journal feature aliases
		"""
		# Create cache key for all features
		cache_key = f"subscription_features_{self.name}"
		
		# Try to get from cache first
		cached_result = frappe.cache().get_value(cache_key)
		if cached_result is not None:
			return cached_result
		
		# If not in cache, calculate the result
		features = []
		if self.features:
			for feature_row in self.features:
				if feature_row.feature:
					journal_feature = frappe.get_doc("Car wash journal feature", feature_row.feature)
					features.append(journal_feature.alias)
		
		# Cache the result for 3 minutes (180 seconds)
		frappe.cache().set_value(cache_key, features, expires_in_sec=180)
		
		return features
	
	def clear_feature_cache(self):
		"""
		Clear all cached feature data for this subscription
		Call this method when subscription features are updated
		"""
		# Clear individual feature checks
		if self.features:
			for feature_row in self.features:
				if feature_row.feature:
					journal_feature = frappe.get_doc("Car wash journal feature", feature_row.feature)
					cache_key = f"subscription_feature_{self.name}_{journal_feature.alias}"
					frappe.cache().delete_value(cache_key)
		
		# Clear all features cache
		cache_key = f"subscription_features_{self.name}"
		frappe.cache().delete_value(cache_key)
	
	def on_update(self):
		"""
		Clear cache when subscription is updated
		"""
		self.clear_feature_cache()
