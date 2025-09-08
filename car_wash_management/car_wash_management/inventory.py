import frappe
from frappe.utils import now_datetime


def recalc_products_totals(doc, products_field: str = "products", services_total_field: str = "services_total", products_total_field: str = "products_total", grand_total_field: str = "grand_total") -> tuple[float, float]:
	"""Ensure each row in products has rate and amount; return (products_total, grand_total).
	If total fields exist on doc, set them.
	"""
	rows = getattr(doc, products_field, None) or []
	total = 0.0
	for row in rows:
		try:
			if not getattr(row, "rate", None):
				default_rate = frappe.db.get_value("Product", row.product, "selling_price") or 0
				row.rate = float(default_rate)
		except Exception:
			pass
		qty = float(getattr(row, "qty", 0) or 0)
		rate = float(getattr(row, "rate", 0) or 0)
		row.amount = float(qty * rate)
		total += float(row.amount or 0)
	try:
		setattr(doc, products_total_field, float(total))
		grand = float(getattr(doc, services_total_field, 0) or 0) + float(total)
		setattr(doc, grand_total_field, grand)
	except Exception:
		pass
	return float(total), float(getattr(doc, grand_total_field, 0) or 0)


def _ensure_bin(warehouse: str, product: str):
	filters = {"warehouse": warehouse, "product": product}
	bin_name = frappe.db.get_value("Bin", filters, "name")
	if not bin_name:
		bin_doc = frappe.get_doc({
			"doctype": "Bin",
			"warehouse": warehouse,
			"product": product,
			"stock_uom": frappe.db.get_value("Product", product, "stock_uom"),
			"actual_qty": 0,
			"reserved_qty": 0,
			"valuation_rate": 0,
		})
		bin_doc.insert(ignore_permissions=True)
		bin_name = bin_doc.name
	return frappe.get_doc("Bin", bin_name)


def available_qty(warehouse: str, product: str) -> float:
	row = frappe.db.get_value(
		"Bin",
		{"warehouse": warehouse, "product": product},
		["actual_qty", "reserved_qty"],
		as_dict=True,
	)
	actual = float((row or {}).get("actual_qty") or 0)
	reserved = float((row or {}).get("reserved_qty") or 0)
	return actual - reserved


def adjust_reserved_qty(warehouse: str, product: str, delta: float) -> None:
	bin_doc = _ensure_bin(warehouse, product)
	bin_doc.reserved_qty = float(bin_doc.reserved_qty or 0) + float(delta)
	if bin_doc.reserved_qty < 0:
		bin_doc.reserved_qty = 0.0
	bin_doc.save(ignore_permissions=True)


def reserve_products(rows: list) -> None:
	for row in rows:
		qty = float(getattr(row, "qty", 0) or 0)
		if qty <= 0:
			continue
		warehouse = getattr(row, "warehouse", None) or frappe.db.get_value("Product", row.product, "default_warehouse")
		if not warehouse:
			frappe.throw(f"Не указан склад для товара {row.product}")
		adjust_reserved_qty(warehouse, row.product, +qty)


def unreserve_products(rows: list) -> None:
	for row in rows:
		qty = float(getattr(row, "qty", 0) or 0)
		if qty <= 0:
			continue
		warehouse = getattr(row, "warehouse", None) or frappe.db.get_value("Product", row.product, "default_warehouse")
		if not warehouse:
			frappe.throw(f"Не указан склад для товара {row.product}")
		adjust_reserved_qty(warehouse, row.product, -qty)


def create_issue_sle(car_wash: str, warehouse: str, product: str, qty: float, rate: float, remarks: str, appointment: str | None = None) -> str:
	sle = frappe.get_doc({
		"doctype": "Stock Ledger Entry",
		"posting_datetime": now_datetime(),
		"purpose": "Material Issue",
		"car_wash": car_wash,
		"warehouse": warehouse,
		"product": product,
		"qty": float(qty),
		"rate": float(rate or 0),
		"remarks": remarks,
	})
	if appointment:
		setattr(sle, "appointment", appointment)
	sle.insert(ignore_permissions=True)
	sle.submit()
	return sle.name


def create_receipt_sle(car_wash: str, warehouse: str, product: str, qty: float, rate: float, remarks: str, appointment: str | None = None) -> str:
	sle = frappe.get_doc({
		"doctype": "Stock Ledger Entry",
		"posting_datetime": now_datetime(),
		"purpose": "Material Receipt",
		"car_wash": car_wash,
		"warehouse": warehouse,
		"product": product,
		"qty": float(qty),
		"rate": float(rate or 0),
		"remarks": remarks,
	})
	if appointment:
		setattr(sle, "appointment", appointment)
	sle.insert(ignore_permissions=True)
	sle.submit()
	return sle.name


def issue_products_from_rows(car_wash: str, rows: list, appointment: str | None = None, release_reserved: bool = True) -> list[str]:
	created = []
	for row in rows:
		qty = float(getattr(row, "qty", 0) or 0)
		if qty <= 0:
			continue
		warehouse = getattr(row, "warehouse", None) or frappe.db.get_value("Product", row.product, "default_warehouse")
		if not warehouse:
			frappe.throw(f"Не указан склад для товара {row.product}")
		# check availability
		avail = available_qty(warehouse, row.product)
		if qty > avail:
			frappe.throw(f"Недостаточно остатков для {row.product} на складе {warehouse}. Доступно: {avail}, требуется: {qty}")
		rate = float(getattr(row, "rate", 0) or 0)
		name = create_issue_sle(car_wash, warehouse, row.product, qty, rate, f"Продажа с назначения {appointment or ''}", appointment=appointment)
		created.append(name)
		if release_reserved:
			try:
				adjust_reserved_qty(warehouse, row.product, -qty)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"Release reserved failed for {row.product} / {warehouse}")
	return created


def cancel_sles_by_appointment(appointment: str) -> None:
	names = frappe.get_all("Stock Ledger Entry", filters={"appointment": appointment}, pluck="name")
	for n in names:
		try:
			doc = frappe.get_doc("Stock Ledger Entry", n)
			if doc.docstatus == 1:
				doc.cancel()
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Cancel SLE failed: {n}")


def reconcile_issues_for_appointment(appt) -> dict:
	"""Delta-reconcile issued stock with current products for a Paid appointment.
	Creates extra Issues for positive deltas and Receipts for negative deltas.
	Returns summary {issued: [...], received: [...]}.
	"""
	rows = getattr(appt, "products", None) or []
	# desired per (product, warehouse)
	desired = {}
	for r in rows:
		qty = float(getattr(r, "qty", 0) or 0)
		if qty <= 0:
			continue
		wh = getattr(r, "warehouse", None) or frappe.db.get_value("Product", r.product, "default_warehouse")
		if not wh:
			frappe.throw(f"Не указан склад для товара {r.product}")
		key = (r.product, wh)
		acc = desired.setdefault(key, {"qty": 0.0, "amount": 0.0})
		rate = float(getattr(r, "rate", 0) or 0)
		acc["qty"] += qty
		acc["amount"] += qty * rate

	# net issued so far per (product, warehouse)
	issued = {}
	for sle in frappe.get_all(
		"Stock Ledger Entry",
		filters={"appointment": appt.name, "docstatus": 1},
		fields=["name", "purpose", "product", "warehouse", "qty", "rate"],
	):
		key = (sle["product"], sle["warehouse"])
		acc = issued.setdefault(key, {"qty": 0.0, "amount": 0.0})
		qty = float(sle["qty"] or 0)
		if sle["purpose"] == "Material Issue":
			acc["qty"] += qty
			acc["amount"] += qty * float(sle["rate"] or 0)
		elif sle["purpose"] == "Material Receipt":
			acc["qty"] -= qty  # receipt reduces net issue
			acc["amount"] -= qty * float(sle["rate"] or 0)

	results = {"issued": [], "received": []}
	for key, want in desired.items():
		prod, wh = key
		want_qty = float(want["qty"])
		have_qty = float((issued.get(key) or {}).get("qty") or 0)
		delta = want_qty - have_qty
		if abs(delta) < 1e-9:
			continue
		# weighted rate for desired or fallback to product selling_price
		rate = 0.0
		if want["qty"] > 0:
			rate = float(want["amount"]) / float(want["qty"]) if want["qty"] else 0.0
		if rate <= 0:
			rate = float(frappe.db.get_value("Product", prod, "selling_price") or 0)
		if delta > 0:
			# need to issue additional quantity, check availability
			avail = available_qty(wh, prod)
			if delta > avail:
				frappe.throw(f"Недостаточно остатков для {prod} на складе {wh}. Доступно: {avail}, требуется дополнительно: {delta}")
			name = create_issue_sle(appt.car_wash, wh, prod, delta, rate, f"Дельта-списание по {appt.name}", appointment=appt.name)
			results["issued"].append(name)
		else:
			# over-issued: receive back (-delta)
			name = create_receipt_sle(appt.car_wash, wh, prod, -delta, rate, f"Дельта-возврат по {appt.name}", appointment=appt.name)
			results["received"].append(name)

	# also handle keys that exist only in issued (when user removed all rows for a product)
	for key, have in issued.items():
		if key in desired:
			continue
		prod, wh = key
		have_qty = float(have["qty"])
		if have_qty > 0:
			# receive back everything
			rate = 0.0
			if have["qty"] > 0:
				rate = float(have["amount"]) / float(have["qty"]) if have["qty"] else 0.0
			name = create_receipt_sle(appt.car_wash, wh, prod, have_qty, rate, f"Дельта-возврат (удалено из заказа) {appt.name}", appointment=appt.name)
			results["received"].append(name)

	return results



