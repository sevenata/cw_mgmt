# Copyright (c) 2025, Rifat and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class CarwashworkerQRtoken(Document):
	pass

import secrets
import frappe
from frappe.utils import now_datetime, add_to_date
from typing import Optional

def _gen_token() -> str:
    return secrets.token_urlsafe(24)

def _get_token_doc(token: str) -> Optional[dict]:
    rows = frappe.get_all(
        "Car wash worker QR token",
        filters={"token": token, "is_revoked": 0},
        fields=["name","worker","expires_at","max_uses","used_count"],
        limit=1,
    )
    return rows[0] if rows else None

def _check_valid(d: dict):
    if not d: frappe.throw("Invalid token", frappe.PermissionError)
    if now_datetime() > d["expires_at"]:
        frappe.throw("Token expired", frappe.PermissionError)
    if int(d["used_count"] or 0) >= int(d["max_uses"] or 0):
        frappe.throw("Token usage limit reached", frappe.PermissionError)

@frappe.whitelist()
def create(worker: str, ttl_minutes: int = 15, max_uses: int = 1):
    token = _gen_token()
    doc = frappe.get_doc({
        "doctype": "Car wash worker QR token",
        "worker": worker,
        "token": token,
        "expires_at": add_to_date(now_datetime(), minutes=ttl_minutes),
        "max_uses": int(max_uses or 1),
        "used_count": 0,
        "issued_by": frappe.session.user,
    })
    doc.insert(ignore_permissions=True)
    
    return {
        "token": token, 
        "expires_at": doc.expires_at,
        "worker": worker
    }

@frappe.whitelist(allow_guest=True)
def verify(token: str, consume: int = 0):
    d = _get_token_doc(token)
    _check_valid(d)
    if int(consume or 0):
        frappe.db.set_value("Car wash worker QR token", d["name"], "used_count", int(d["used_count"] or 0) + 1)
    return {
        "worker": d["worker"],
        "expires_at": d["expires_at"],
        "remaining_uses": int(d["max_uses"] or 0) - int(d["used_count"] or 0),
    }

@frappe.whitelist(allow_guest=True)
def get_balance(token: str):
    info = verify(token, consume=0)
    from car_wash_management.car_wash_management.doctype.worker_ledger_entry.worker_ledger_entry import get_worker_balance
    
    # Get worker information
    worker_info = frappe.get_value(
        "Car wash worker",
        info["worker"],
        ["full_name", "first_name", "last_name", "car_wash", "car_wash_title"],
        as_dict=True
    )
    
    balance = get_worker_balance(info["worker"])
    
    return {
        **balance,
        "worker_info": {
            "name": info["worker"],
            "full_name": worker_info.get("full_name") if worker_info else "",
            "first_name": worker_info.get("first_name") if worker_info else "",
            "last_name": worker_info.get("last_name") if worker_info else "",
            "car_wash": worker_info.get("car_wash") if worker_info else "",
            "car_wash_title": worker_info.get("car_wash_title") if worker_info else "",
        }
    }

@frappe.whitelist(allow_guest=True)
def get_ledger(token: str, limit: int = 50):
    info = verify(token, consume=0)
    from car_wash_management.car_wash_management.doctype.worker_ledger_entry.worker_ledger_entry import get_worker_ledger
    return get_worker_ledger(info["worker"], limit=int(limit or 50))