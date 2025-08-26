# Copyright (c) 2025, Rifat and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class StockLedgerEntry(Document):
	def validate(self):
		try:
			purpose = getattr(self, "purpose", None)
			qty = float(getattr(self, "qty", 0) or 0)
			if qty == 0:
				raise frappe.ValidationError("Количество должно быть больше 0")
			if purpose == "Material Transfer":
				if not getattr(self, "from_warehouse", None) or not getattr(self, "to_warehouse", None):
					raise frappe.ValidationError("Укажите склад-источник и склад-назначение для перемещения")
				if getattr(self, "from_warehouse") == getattr(self, "to_warehouse"):
					raise frappe.ValidationError("Склады-источник и назначения должны отличаться")
			else:
				if not getattr(self, "warehouse", None):
					raise frappe.ValidationError("Укажите склад")
		except frappe.ValidationError:
			raise
		except Exception:
			frappe.log_error(frappe.get_traceback(), "SLE validate failed")
			raise
	def on_submit(self):
		try:
			print(f"[SLE.on_submit] name={self.name}, purpose={getattr(self, 'purpose', None)}, wh={getattr(self, 'warehouse', None)}, from={getattr(self, 'from_warehouse', None)}, to={getattr(self, 'to_warehouse', None)}, product={self.product}, qty={self.qty}")
			_apply_stock_movement(self, is_cancel=False)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "SLE on_submit failed")

	def on_cancel(self):
		try:
			print(f"[SLE.on_cancel] name={self.name}, purpose={getattr(self, 'purpose', None)}, wh={getattr(self, 'warehouse', None)}, from={getattr(self, 'from_warehouse', None)}, to={getattr(self, 'to_warehouse', None)}, product={self.product}, qty={self.qty}")
			_apply_stock_movement(self, is_cancel=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "SLE on_cancel failed")


def _apply_stock_movement(doc: Document, is_cancel: bool = False) -> None:
	"""Apply stock movement based on purpose: Receipt/Issue/Transfer.

	On cancel, invert movement. Maintains simple moving average valuation_rate on receipts.
	"""
	qty = float(doc.qty or 0)
	if qty == 0:
		print("[_apply_stock_movement] Skip: qty == 0")
		return

	purpose = getattr(doc, "purpose", None)

	def adjust_bin(warehouse: str, product: str, delta: float, set_rate: float | None = None):
		filters = {"warehouse": warehouse, "product": product}
		bin_name = frappe.db.get_value("Bin", filters, "name")
		if not bin_name:
			print(f"[_apply_stock_movement.adjust_bin] Create Bin wh={warehouse}, product={product}, delta={delta}")
			bin_doc = frappe.new_doc("Bin")
			bin_doc.warehouse = warehouse
			bin_doc.product = product
			try:
				product_uom = frappe.db.get_value("Product", product, "stock_uom")
			except Exception:
				product_uom = None
			bin_doc.stock_uom = product_uom
			bin_doc.actual_qty = float(delta)
			bin_doc.reserved_qty = 0
			if set_rate is not None:
				bin_doc.valuation_rate = float(set_rate)
			bin_doc.insert(ignore_permissions=True)
		else:
			bin_doc = frappe.get_doc("Bin", bin_name)
			bin_doc.actual_qty = float(bin_doc.actual_qty or 0) + float(delta)
			if set_rate is not None:
				bin_doc.valuation_rate = float(set_rate)
			bin_doc.save(ignore_permissions=True)

	if purpose == "Material Receipt":
		delta = -qty if is_cancel else qty
		# moving average valuation on receipt (only when applying, not cancelling)
		new_rate = None
		if not is_cancel:
			try:
				row = frappe.db.get_value(
					"Bin",
					{"warehouse": doc.warehouse, "product": doc.product},
					["valuation_rate", "actual_qty"],
					as_dict=True,
				)
				old_rate = float((row or {}).get("valuation_rate") or 0)
				old_qty = float((row or {}).get("actual_qty") or 0)
				rate = float(getattr(doc, "rate", 0) or 0)
				amount = rate * qty
				new_qty = max(old_qty + qty, 0.0)
				if new_qty > 0:
					new_rate = (old_rate * old_qty + amount) / new_qty
			except Exception:
				new_rate = None
		adjust_bin(doc.warehouse, doc.product, delta, set_rate=(new_rate if not is_cancel else None))

	elif purpose == "Material Issue":
		delta = qty if is_cancel else -qty
		adjust_bin(doc.warehouse, doc.product, delta)

	elif purpose == "Material Transfer":
		from_wh = getattr(doc, "from_warehouse", None)
		to_wh = getattr(doc, "to_warehouse", None)
		if not from_wh or not to_wh:
			raise frappe.ValidationError("Both from_warehouse and to_warehouse must be set for Material Transfer")
		# On apply: -qty from source, +qty to target. On cancel: reverse.
		source_delta = qty if is_cancel else -qty
		target_delta = -source_delta
		adjust_bin(from_wh, doc.product, source_delta)
		adjust_bin(to_wh, doc.product, target_delta)

	elif purpose == "Stock Reconciliation":
		# Set absolute quantity to provided qty on apply; on cancel we can't recover old absolute without history, so skip.
		if not is_cancel:
			filters = {"warehouse": doc.warehouse, "product": doc.product}
			bin_name = frappe.db.get_value("Bin", filters, "name")
			if not bin_name:
				bin_doc = frappe.new_doc("Bin")
				bin_doc.warehouse = doc.warehouse
				bin_doc.product = doc.product
				try:
					product_uom = frappe.db.get_value("Product", doc.product, "stock_uom")
				except Exception:
					product_uom = None
				bin_doc.stock_uom = product_uom
				bin_doc.actual_qty = qty
				bin_doc.reserved_qty = 0
				bin_doc.insert(ignore_permissions=True)
			else:
				bin_doc = frappe.get_doc("Bin", bin_name)
				bin_doc.actual_qty = qty
				bin_doc.save(ignore_permissions=True)
	else:
		raise frappe.ValidationError(f"Unsupported purpose: {purpose}")
