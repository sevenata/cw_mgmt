# car_wash/tariffs.py
import frappe

def ensure_tariff_valid_for_car_wash(tariff_id: str, car_wash: str) -> str:
    """
    Проверяем, что тариф существует, активен и принадлежит указанной мойке.
    Возвращаем name (тот же tariff_id), либо бросаем frappe.throw.
    """
    row = frappe.db.get_value(
        "Car wash tariff",
        tariff_id,
        ["name", "car_wash", "is_active"],
        as_dict=True,
    )
    if not row:
        frappe.throw(f"Tariff '{tariff_id}' not found.")
    if row.car_wash != car_wash:
        frappe.throw(f"Tariff '{tariff_id}' does not belong to car wash '{car_wash}'.")
    if not row.is_active:
        frappe.throw(f"Tariff '{tariff_id}' is not active.")
    return row.name


def resolve_applicable_tariff(car_wash: str, car: str | None = None, services: list | None = None) -> str:
    """
    Базовый авто-подбор тарифа: берём активный с максимальным priority.
    Сюда позже можно добавить проверку child-таблицы `Car wash tariff filter`.
    """
    rows = frappe.get_all(
        "Car wash tariff",
        filters={"car_wash": car_wash, "is_active": 1},
        fields=["name", "priority"],
        order_by="priority desc, modified desc",
        limit_page_length=50,
    )
    if not rows:
        frappe.throw("No active tariff found for this car wash.")
    return rows[0].name
