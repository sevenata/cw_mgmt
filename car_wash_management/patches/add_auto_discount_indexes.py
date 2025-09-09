import frappe


def _index_exists(table: str, index_name: str) -> bool:
    exists = frappe.db.sql(
        """
        SELECT 1
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND INDEX_NAME = %s
        LIMIT 1
        """,
        (table, index_name),
    )
    return bool(exists)


def _ensure_index(table: str, index_name: str, columns_sql: str) -> None:
    if not _index_exists(table, index_name):
        frappe.db.sql(f"ALTER TABLE `{table}` ADD INDEX `{index_name}` ({columns_sql})")


def execute():
    table = "tabCar wash auto discount"

    # Composite index to speed up common filters and ordering
    _ensure_index(
        table,
        "idx_cwad_cw_active_deleted_priority",
        "`car_wash`, `is_active`, `is_deleted`, `priority`",
    )

    # Helpful single-column indexes (defensive, cheap)
    _ensure_index(table, "idx_cwad_car_wash", "`car_wash`")
    _ensure_index(table, "idx_cwad_is_active", "`is_active`")
    _ensure_index(table, "idx_cwad_is_deleted", "`is_deleted`")
    _ensure_index(table, "idx_cwad_priority", "`priority`")

    frappe.db.commit()



