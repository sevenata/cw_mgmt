# Copyright (c) 2025, Rifat and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Product(Document):
	def after_insert(self):
		"""Auto-create SLE for opening stock on default warehouse."""
		opening_stock = float(self.opening_stock or 0)
		default_warehouse = getattr(self, "default_warehouse", None)
		print(f"[Product.after_insert] name={self.name}, car_wash={self.car_wash}, default_warehouse={default_warehouse}, opening_stock={opening_stock}, uom={getattr(self, 'stock_uom', None)}")
		if opening_stock <= 0 or not default_warehouse:
			print("[Product.after_insert] Skip opening SLE: no default_warehouse or opening_stock <= 0")
			return

		uom = getattr(self, "stock_uom", None)
		# Validate links early to avoid silent failure in after_commit
		if not frappe.db.exists("Warehouse", default_warehouse):
			frappe.log_error(f"Default warehouse not found: {default_warehouse}", "Product opening stock SLE skipped")
			return
		if self.car_wash and not frappe.db.exists("Car wash", self.car_wash):
			frappe.log_error(f"Car wash not found: {self.car_wash}", "Product opening stock SLE skipped")
			return

		# Run after COMMIT to ensure Product exists and indexes are ready
		def _run():
			print(f"[Product.after_insert.after_commit] Creating opening SLE for product={self.name}, wh={default_warehouse}, qty={opening_stock}")
			create_opening_sle(
				product_name=self.name,
				car_wash=self.car_wash,
				warehouse=default_warehouse,
				qty=opening_stock,
				uom=uom,
				opening_rate=getattr(self, "opening_rate", None),
			)

		frappe.db.after_commit(_run)


@frappe.whitelist()
def create_opening_sle(product_name: str, car_wash: str, warehouse: str, qty: float, uom: str | None = None, opening_rate: float | None = None):
	"""Create and submit SLE for opening stock. Intended to be called post-commit."""
	try:
		from frappe.utils import now_datetime
		# validate links, try to recover car_wash from warehouse if not provided
		if not frappe.db.exists("Product", product_name):
			frappe.log_error(f"Product not found: {product_name}", "Opening SLE skipped")
			return
		if not frappe.db.exists("Warehouse", warehouse):
			frappe.log_error(f"Warehouse not found: {warehouse}", "Opening SLE skipped")
			return
		if not car_wash:
			car_wash = frappe.db.get_value("Warehouse", warehouse, "car_wash")
		if car_wash and not frappe.db.exists("Car wash", car_wash):
			frappe.log_error(f"Car wash not found: {car_wash}", "Opening SLE skipped")
			return
		print(f"[create_opening_sle] Preparing SLE product={product_name}, wh={warehouse}, qty={qty}, uom={uom}, car_wash={car_wash}")
		sle = frappe.new_doc("Stock Ledger Entry")
		sle.purpose = "Material Receipt"
		sle.car_wash = car_wash
		sle.warehouse = warehouse
		sle.product = product_name
		sle.qty = float(qty or 0)
		sle.uom = uom
		# Opening receipt can carry valuation rate
		if opening_rate is None:
			try:
				opening_rate = float(frappe.db.get_value("Product", product_name, "opening_rate") or 0)
			except Exception:
				opening_rate = 0.0
		try:
			sle.rate = float(opening_rate or 0)
		except Exception:
			sle.rate = 0.0
		sle.amount = float(sle.rate) * float(qty or 0)
		sle.posting_datetime = now_datetime()
		sle.remarks = f"Opening stock for product {product_name}"
		print("[create_opening_sle] Inserting SLE (draft)")
		# Ensure permissions are bypassed for programmatic creation and submission
		sle.flags.ignore_permissions = True
		sle.insert(ignore_permissions=True)
		print(f"[create_opening_sle] Submitting SLE name={sle.name}")
		sle.submit()
		print(f"[create_opening_sle] Submitted SLE name={sle.name}, docstatus={sle.docstatus}")
		# Since this runs inside an after-commit callback, explicitly commit so the SLE persists
		frappe.db.commit()
		frappe.logger().info(f"Opening SLE created for product={product_name}, warehouse={warehouse}, qty={qty}")
	except Exception:
		print('erer')
		frappe.log_error(frappe.get_traceback(), "Product opening stock SLE failed")
