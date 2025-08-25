# Copyright (c) 2025, Rifat and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class StockLedgerEntry(Document):
	def on_submit(self):
		try:
			print(f"[SLE.on_submit] name={self.name}, wh={self.warehouse}, product={self.product}, qty={self.qty}, uom={getattr(self, 'uom', None)}")
			_update_bin_qty(self, is_cancel=False)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "SLE on_submit failed")

	def on_cancel(self):
		try:
			print(f"[SLE.on_cancel] name={self.name}, wh={self.warehouse}, product={self.product}, qty={self.qty}")
			_update_bin_qty(self, is_cancel=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "SLE on_cancel failed")


def _update_bin_qty(doc: Document, is_cancel: bool = False) -> None:
	"""Update or create Bin for (warehouse, product) and adjust actual_qty."""
	qty = float(doc.qty or 0)
	if qty == 0:
		print("[_update_bin_qty] Skip: qty == 0")
		return
	qty_delta = -qty if is_cancel else qty

	# Maintain simple moving average valuation_rate on receipt
	new_rate = None
	if not is_cancel and getattr(doc, "purpose", None) == "Material Receipt":
		try:
			old_name = frappe.db.get_value("Bin", {"warehouse": doc.warehouse, "product": doc.product}, "name")
			old_rate = 0.0
			old_qty = 0.0
			if old_name:
				row = frappe.db.get_value("Bin", {"name": old_name}, ["valuation_rate", "actual_qty"], as_dict=True)
				if row:
					old_rate = float(row.get("valuation_rate") or 0)
					old_qty = float(row.get("actual_qty") or 0)

			rate = float(getattr(doc, "rate", 0) or 0)
			amount = rate * qty
			new_qty = max(old_qty + qty, 0.0)
			if new_qty > 0:
				new_rate = (old_rate * old_qty + amount) / new_qty
		except Exception:
			new_rate = None

	filters = {"warehouse": doc.warehouse, "product": doc.product}
	bin_name = frappe.db.get_value("Bin", filters, "name")
	if not bin_name:
		print(f"[_update_bin_qty] No Bin, creating new for wh={doc.warehouse}, product={doc.product}")
		bin_doc = frappe.new_doc("Bin")
		bin_doc.warehouse = doc.warehouse
		bin_doc.product = doc.product
		bin_doc.stock_uom = getattr(doc, "uom", None)
		bin_doc.actual_qty = qty_delta
		bin_doc.reserved_qty = 0
		bin_doc.valuation_rate = float(new_rate or 0) if (not is_cancel and getattr(doc, "purpose", None) == "Material Receipt") else 0
		bin_doc.insert(ignore_permissions=True)
	else:
		print(f"[_update_bin_qty] Update existing Bin={bin_name} with delta={qty_delta}")
		bin_doc = frappe.get_doc("Bin", bin_name)
		bin_doc.actual_qty = float(bin_doc.actual_qty or 0) + qty_delta
		if not is_cancel and getattr(doc, "purpose", None) == "Material Receipt" and new_rate is not None:
			bin_doc.valuation_rate = float(new_rate)
		bin_doc.save(ignore_permissions=True)
