import frappe
from typing import Any, Dict, List, Optional, Tuple


# Fields selected for batched hydration
CLIENT_FIELDS: List[str] = [
	"name",
	"customer_name",
	"phone",
	"user",
	"image",
]

CAR_FIELDS: List[str] = [
	"name",
	"customer",
	"license_plate",
	"make",
	"make_name",
	"model",
	"model_name",
	"body_type",
	"year",
	"color",
]

DESCRIPTION_FIELDS: List[str] = [
	"name",
	"client",
	"car_wash",
	"company",
	"first_name",
	"last_name",
	"description",
]


def _ensure_car_wash_provided(car_wash: str) -> None:
	"""Validate required input parameters."""
	if not car_wash:
		raise frappe.ValidationError("car_wash is required")


def _build_search_clauses_and_params(query: Optional[str], car_wash: str) -> Tuple[str, Dict[str, Any]]:
	"""Build base WHERE clause and SQL params for the clients list query.

	Uses EXISTS in subqueries to avoid heavy JOINs and duplicate rows when filtering
	by cars and client descriptions.
	"""
	params: Dict[str, Any] = {"car_wash": car_wash}
	where_parts: List[str] = ["1=1"]

	if query:
		params["q"] = f"%{query}%"
		exists_car = (
			"EXISTS ("
			"SELECT 1 FROM `tabCar wash car` car "
			"WHERE car.customer = c.name AND car.is_deleted = 0 "
			"AND car.license_plate LIKE %(q)s)"
		)
		exists_desc = (
			"EXISTS ("
			"SELECT 1 FROM `tabCar wash client description` d "
			"WHERE d.client = c.name AND d.car_wash = %(car_wash)s "
			"AND (d.first_name LIKE %(q)s OR d.last_name LIKE %(q)s))"
		)
		where_parts.append(
			"(" 
			"c.customer_name LIKE %(q)s OR "
			"c.phone LIKE %(q)s OR "
			f"{exists_car} OR "
			f"{exists_desc}"
			")"
		)

	return " AND ".join(where_parts), params


def _maybe_count_total(where_sql: str, params: Dict[str, Any], include_total: int) -> int:
	"""Return total count of clients if requested, without any JOINs."""
	if not bool(int(include_total)):
		return 0
	count_sql = f"""
		SELECT COUNT(*)
		FROM `tabCar wash client` c
		WHERE {where_sql}
	"""
	return int(frappe.db.sql(count_sql, params)[0][0])


def _build_cursor_filter(cursor_modified: Optional[str], cursor_name: Optional[str], params: Dict[str, Any]) -> str:
	"""Create keyset pagination cursor filter and enrich params if cursor provided."""
	extra_where = ""
	if cursor_modified and cursor_name:
		extra_where = (
			" AND (c.modified < %(cursor_modified)s OR (c.modified = %(cursor_modified)s AND c.name < %(cursor_name)s))"
		)
		params["cursor_modified"] = cursor_modified
		params["cursor_name"] = cursor_name
	return extra_where


def _fetch_client_rows(where_sql: str, extra_where: str, params: Dict[str, Any], limit: int) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, str]], List[str]]:
	"""Fetch client rows using keyset pagination and compute next cursor."""
	page_size = int(limit)
	params["limit"] = page_size + 1  # fetch one extra to detect existence of the next page
	list_sql = f"""
		SELECT c.name, c.customer_name, c.phone, c.user, c.image, c.modified
		FROM `tabCar wash client` c
		WHERE {where_sql}{extra_where}
		ORDER BY c.modified DESC, c.name DESC
		LIMIT %(limit)s
	"""
	rows: List[Dict[str, Any]] = frappe.db.sql(list_sql, params, as_dict=1)

	next_cursor: Optional[Dict[str, str]] = None
	if len(rows) > page_size:
		last_row = rows[page_size - 1]
		next_cursor = {"modified": str(last_row.get("modified")), "name": last_row.get("name")}
		rows = rows[:page_size]

	client_names = [r["name"] for r in rows]
	return rows, next_cursor, client_names


def _map_clients(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
	"""Map client name to a reduced client dict with selected fields only."""
	return {r["name"]: {f: r.get(f) for f in CLIENT_FIELDS} for r in rows}


def _fetch_cars_by_customer(client_names: List[str]) -> Dict[str, List[Dict[str, Any]]]:
	"""Batch-fetch cars for provided client names."""
	cars_by_customer: Dict[str, List[Dict[str, Any]]] = {}
	if not client_names:
		return cars_by_customer
	for car_row in frappe.get_all(
		"Car wash car",
		filters={"customer": ["in", client_names], "is_deleted": 0},
		fields=CAR_FIELDS,
	):
		cars_by_customer.setdefault(car_row.get("customer"), []).append(car_row)
	return cars_by_customer


def _fetch_latest_descriptions(client_names: List[str], car_wash: str) -> Dict[str, Dict[str, Any]]:
	"""Fetch descriptions for the given car wash and return only the latest per client."""
	if not client_names:
		return {}
	rows: List[Dict[str, Any]] = frappe.db.sql(
		"""
		SELECT d1.name, d1.client, d1.car_wash, d1.company, d1.first_name, d1.last_name, d1.description, d1.modified
		FROM `tabCar wash client description` d1
		JOIN (
			SELECT client, MAX(modified) AS max_modified
			FROM `tabCar wash client description`
			WHERE client IN %(clients)s AND car_wash = %(car_wash)s
			GROUP BY client
		) d2 ON d1.client = d2.client AND d1.modified = d2.max_modified
		WHERE d1.car_wash = %(car_wash)s
		""",
		{"clients": tuple(client_names), "car_wash": car_wash},
		as_dict=1,
	)
	latest_desc_by_client: Dict[str, Dict[str, Any]] = {}
	for d in rows:
		cid = d.get("client")
		if cid not in latest_desc_by_client:
			latest_desc_by_client[cid] = {f: d.get(f) for f in DESCRIPTION_FIELDS + ["modified"]}
	return latest_desc_by_client


def _fetch_tags_for_descriptions(latest_desc_by_client: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
	"""Fetch tags for all latest descriptions and group by description (parent)."""
	all_desc_names = [d.get("name") for d in latest_desc_by_client.values() if d.get("name")]
	tags_by_parent: Dict[str, List[Dict[str, Any]]] = {}
	if not all_desc_names:
		return tags_by_parent

	rows = frappe.db.sql(
		"""
		SELECT dt.parent AS parent, dt.tag AS tag, t.title AS tag_title, IFNULL(t.color, '') AS color
		FROM `tabCar wash client description tag` dt
		JOIN `tabCar wash tag` t ON t.name = dt.tag
		WHERE dt.parent IN %(parents)s
		ORDER BY t.title ASC
		""",
		{"parents": tuple(all_desc_names)},
		as_dict=1,
	)
	for r in rows:
		tags_by_parent.setdefault(r.get("parent"), []).append({
			"tag": r.get("tag"),
			"tag_title": r.get("tag_title"),
			"color": r.get("color") or "",
		})
	return tags_by_parent


def _assemble_items(
	client_names: List[str],
	clients_map: Dict[str, Dict[str, Any]],
	cars_by_customer: Dict[str, List[Dict[str, Any]]],
	latest_desc_by_client: Dict[str, Dict[str, Any]],
	tags_by_parent: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
	"""Assemble final items list for the response payload."""
	items: List[Dict[str, Any]] = []
	for client_name in client_names:
		client_doc = clients_map.get(client_name) or {}
		cars = cars_by_customer.get(client_name, [])
		desc = latest_desc_by_client.get(client_name)
		if desc:
			desc_name = desc.get("name")
			desc["tags"] = tags_by_parent.get(desc_name, [])
		items.append({
			"client": client_doc,
			"cars": cars,
			"description": desc,
		})
	return items


def search_clients(
	car_wash: str,
	query: str | None = None,
	limit: int = 50,
	include_total: int = 1,
	cursor_modified: str | None = None,
	cursor_name: str | None = None,
):
	"""Search car wash clients with keyset pagination and batched hydration.

	Parameters:
		car_wash: Required car wash name to scope the search.
		query: Optional string to match against customer name, phone, car plate, or description first/last name.
		limit: Page size for keyset pagination.
		include_total: If truthy, also compute total count of matching clients.
		cursor_modified: Keyset pagination cursor (modified timestamp of last item).
		cursor_name: Keyset pagination cursor (name of last item).

	Returns:
		Dict with keys: total (int), items (list), next_cursor (dict | None)
	"""
	_ensure_car_wash_provided(car_wash)

	where_sql, params = _build_search_clauses_and_params(query, car_wash)
	total = _maybe_count_total(where_sql, params, include_total)
	extra_where = _build_cursor_filter(cursor_modified, cursor_name, params)

	limit = max(1, min(int(limit or 50), 200))
	client_rows, next_cursor, client_names = _fetch_client_rows(where_sql, extra_where, params, limit)
	if not client_names:
		return {"total": int(total or 0), "items": []}

	clients_map = _map_clients(client_rows)
	cars_by_customer = _fetch_cars_by_customer(client_names)
	latest_desc_by_client = _fetch_latest_descriptions(client_names, car_wash)
	tags_by_parent = _fetch_tags_for_descriptions(latest_desc_by_client)

	items = _assemble_items(
		client_names=client_names,
		clients_map=clients_map,
		cars_by_customer=cars_by_customer,
		latest_desc_by_client=latest_desc_by_client,
		tags_by_parent=tags_by_parent,
	)

	return {"total": int(total or 0), "items": items, "next_cursor": next_cursor}


