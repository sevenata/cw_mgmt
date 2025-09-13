import frappe


def execute():
	# Create helpful indexes for search performance. Use IF NOT EXISTS where supported.
	# Frappe uses MariaDB/MySQL; IF NOT EXISTS for indexes is available in MySQL 8+, MariaDB 10.5+.
	# For broader compatibility, wrap in try/except.
	_statements = [
		"""
		CREATE INDEX idx_cw_client_modified_name
		ON `tabCar wash client` (modified DESC, name DESC)
		""",
		"""
		CREATE INDEX idx_cw_client_customer_name
		ON `tabCar wash client` (customer_name)
		""",
		"""
		CREATE INDEX idx_cw_client_phone
		ON `tabCar wash client` (phone)
		""",
		"""
		CREATE INDEX idx_cw_car_customer_deleted
		ON `tabCar wash car` (customer, is_deleted)
		""",
		"""
		CREATE INDEX idx_cw_car_license_plate
		ON `tabCar wash car` (license_plate)
		""",
		"""
		CREATE INDEX idx_cw_desc_client_wash_modified
		ON `tabCar wash client description` (client, car_wash, modified)
		""",
		"""
		CREATE INDEX idx_cw_desc_tag_parent
		ON `tabCar wash client description tag` (parent)
		""",
		"""
		CREATE INDEX idx_cw_desc_tag_tag
		ON `tabCar wash client description tag` (tag)
		""",
	]

	for stmt in _statements:
		try:
			frappe.db.sql(stmt)
		except Exception:
			frappe.db.rollback()
			# Ignore if index already exists or DB doesn't support the exact syntax
			# We deliberately swallow errors here to keep patch idempotent across environments
			pass


