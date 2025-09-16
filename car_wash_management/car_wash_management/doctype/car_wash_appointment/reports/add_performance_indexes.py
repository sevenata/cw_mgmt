# car_wash_management/car_wash_management/car_wash_management/doctype/car_wash_appointment/reports/add_performance_indexes.py
"""
Скрипт для добавления индексов для оптимизации производительности weekly_owner_report.py
Запускать через: bench execute car_wash_management.car_wash_management.doctype.car_wash_appointment.reports.add_performance_indexes.add_indexes
"""

import frappe


def add_indexes():
    """
    Добавляет индексы для оптимизации запросов в weekly_owner_report.py
    """
    indexes = [
        {
            "table": "tabCar wash appointment",
            "name": "idx_appointment_car_wash_starts",
            "columns": ["car_wash", "starts_on", "is_deleted"],
            "description": "Оптимизирует фильтрацию по мойке, дате и статусу удаления"
        },
        {
            "table": "tabCar wash appointment", 
            "name": "idx_appointment_payment",
            "columns": ["payment_status", "payment_type"],
            "description": "Оптимизирует группировку по статусу и типу оплаты"
        },
        {
            "table": "tabCar wash appointment",
            "name": "idx_appointment_worker",
            "columns": ["car_wash_worker", "car_wash"],
            "description": "Оптимизирует группировку по работникам"
        },
        {
            "table": "tabCar wash box",
            "name": "idx_box_car_wash_status",
            "columns": ["car_wash", "is_deleted", "is_disabled"],
            "description": "Оптимизирует получение активных боксов мойки"
        }
    ]
    
    created_count = 0
    skipped_count = 0
    
    for index in indexes:
        try:
            if _index_exists(index["table"], index["name"]):
                print(f"✅ Индекс {index['name']} уже существует, пропускаем")
                skipped_count += 1
                continue
                
            _create_index(index)
            print(f"✅ Создан индекс {index['name']} для таблицы {index['table']}")
            created_count += 1
            
        except Exception as e:
            print(f"❌ Ошибка при создании индекса {index['name']}: {str(e)}")
    
    print(f"\n📊 Результат:")
    print(f"   Создано индексов: {created_count}")
    print(f"   Пропущено (уже существуют): {skipped_count}")
    print(f"   Всего обработано: {len(indexes)}")


def _index_exists(table: str, index_name: str) -> bool:
    """Проверяет существование индекса"""
    try:
        result = frappe.db.sql(f"""
            SELECT COUNT(*) as count 
            FROM information_schema.statistics 
            WHERE table_schema = DATABASE() 
            AND table_name = '{table.replace('tab', '')}' 
            AND index_name = '{index_name}'
        """)
        return result[0][0] > 0
    except Exception:
        return False


def _create_index(index: dict):
    """Создает индекс в базе данных"""
    columns_str = ", ".join(index["columns"])
    
    frappe.db.sql(f"""
        CREATE INDEX `{index["name"]}` 
        ON `{index["table"]}` ({columns_str})
    """)
    
    # Обновляем кэш индексов
    frappe.db.commit()


def remove_indexes():
    """
    Удаляет созданные индексы (для отката)
    """
    indexes_to_remove = [
        ("tabCar wash appointment", "idx_appointment_car_wash_starts"),
        ("tabCar wash appointment", "idx_appointment_payment"), 
        ("tabCar wash appointment", "idx_appointment_worker"),
        ("tabCar wash box", "idx_box_car_wash_status")
    ]
    
    removed_count = 0
    
    for table, index_name in indexes_to_remove:
        try:
            if _index_exists(table, index_name):
                frappe.db.sql(f"DROP INDEX `{index_name}` ON `{table}`")
                print(f"✅ Удален индекс {index_name}")
                removed_count += 1
            else:
                print(f"ℹ️  Индекс {index_name} не найден")
        except Exception as e:
            print(f"❌ Ошибка при удалении индекса {index_name}: {str(e)}")
    
    print(f"\n📊 Удалено индексов: {removed_count}")


if __name__ == "__main__":
    add_indexes()
