# Copyright (c) 2024, Rifat Dzhumagulov and contributors
# For license information, please see license.txt

import frappe
import json
from frappe.model.document import Document


class Carmake(Document):
	pass

@frappe.whitelist()
def get_car_make_synonyms():
    cache_key = "car_make_synonyms_cache"

    # Try to fetch from cache
    cached_result = frappe.cache().get_value(cache_key)
    if cached_result:
        return json.loads(cached_result)

    # Fetch all Car make records
    car_makes = frappe.get_all("Car make", fields=["name", "title", "alias"])

    # Fetch all synonyms in one query
    synonyms_records = frappe.get_all(
        "Car model synonym",
        fields=["parent", "synonym"],
        filters={"parenttype": "Car make"}
    )

    # Map synonyms by parent
    synonyms_map = {}
    for record in synonyms_records:
        synonyms_map.setdefault(record["parent"], []).append(record["synonym"])

    # Build result list
    result = []
    for make in car_makes:
        result.append({
            "name": make["name"],
            "title": make["title"],
            "alias": make["alias"],
            "synonyms": synonyms_map.get(make["name"], [])
        })

    # Store in cache for 1 hour (3600 seconds)
    frappe.cache().set_value(cache_key, json.dumps(result), expires_in_sec=3600)

    return result
