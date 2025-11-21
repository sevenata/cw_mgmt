# car_wash_management/tasks/daily_reports.py
"""
Daily Telegram reports for car wash management.
Sends formatted daily statistics reports to Telegram at end of business day.
"""

import frappe
import requests
from frappe.utils import today, getdate, get_time, now_datetime, flt
from datetime import datetime


def send_daily_telegram_reports():
    """
    Scheduled task to send daily car wash reports to Telegram.
    Runs hourly to check if it's time to send reports based on each car wash's configured report time.
    """
    try:
        frappe.logger().info("[Telegram Daily Reports] Starting scheduled task")
        
        # Get current time
        current_time = now_datetime().time()
        current_date = today()
        
        # Get all active car washes
        car_washes = frappe.get_all(
            "Car wash",
            filters={"is_deleted": 0},
            fields=[
                "name", 
                "title", 
                "telegram_chat_id", 
                "telegram_report_enabled",
                "telegram_report_time"
            ]
        )
        
        if not car_washes:
            frappe.logger().info("[Telegram Daily Reports] No car washes found")
            return
        
        sent_count = 0
        skipped_count = 0
        
        for car_wash in car_washes:
            try:
                # Skip if Telegram reports are disabled for this car wash
                if not car_wash.get("telegram_report_enabled"):
                    skipped_count += 1
                    continue
                
                # Check if it's time to send the report (end of business day)
                report_time = car_wash.get("telegram_report_time")
                if not report_time:
                    # Skip if report time is not configured (required for end of business day reporting)
                    skipped_count += 1
                    continue
                
                # Parse the time string (format: "HH:MM:SS" or "HH:MM")
                try:
                    if isinstance(report_time, str):
                        report_time_obj = get_time(report_time)
                    else:
                        report_time_obj = report_time
                    
                    # Check if current time matches report time (within 30 minutes window for hourly scheduler)
                    # Compare only the time portion, ignoring the date
                    current_datetime = datetime.combine(datetime.today(), current_time)
                    report_datetime = datetime.combine(datetime.today(), report_time_obj)
                    time_diff = abs((current_datetime - report_datetime).total_seconds())
                    
                    # Only send if we're within 30 minutes of the target time
                    if time_diff > 1800:  # 30 minutes in seconds
                        continue
                except Exception as e:
                    frappe.logger().warning(f"[Telegram Daily Reports] Invalid report_time for {car_wash.name}: {str(e)}")
                    skipped_count += 1
                    continue
                
                # Get chat ID with fallback to global default from JWT Settings
                chat_id = car_wash.get("telegram_chat_id")
                if not chat_id:
                    # Try to get from JWT Settings (global fallback)
                    try:
                        jwt_settings = frappe.get_single("JWT Settings")
                        chat_id = jwt_settings.get("telegram_default_chat_id")
                    except Exception as e:
                        frappe.logger().debug(f"[Telegram Daily Reports] Could not get JWT Settings: {str(e)}")
                        chat_id = None
                
                if not chat_id:
                    frappe.logger().warning(f"[Telegram Daily Reports] No Telegram chat ID for car wash {car_wash.name}")
                    skipped_count += 1
                    continue
                
                # Generate daily report
                report_data = generate_daily_report(car_wash.name, current_date)
                
                if not report_data:
                    frappe.logger().warning(f"[Telegram Daily Reports] No data generated for car wash {car_wash.name}")
                    skipped_count += 1
                    continue
                
                # Format and send to Telegram
                car_wash_name = car_wash.get("title") or car_wash.name
                message = format_telegram_message(report_data, car_wash_name)
                
                success = send_telegram_message(chat_id, message)
                
                if success:
                    sent_count += 1
                    frappe.logger().info(f"[Telegram Daily Reports] Report sent for car wash {car_wash.name}")
                else:
                    frappe.logger().error(f"[Telegram Daily Reports] Failed to send report for car wash {car_wash.name}")
                    
            except Exception as e:
                frappe.log_error(
                    f"Error processing car wash {car_wash.name}: {frappe.get_traceback()}",
                    "Telegram Daily Reports Error"
                )
                continue
        
        frappe.logger().info(
            f"[Telegram Daily Reports] Completed: {sent_count} sent, {skipped_count} skipped"
        )
        
    except Exception as e:
        frappe.log_error(
            f"Error in send_daily_telegram_reports: {frappe.get_traceback()}",
            "Daily Telegram Reports Error"
        )


def generate_daily_report(car_wash: str, date: str) -> dict:
    """
    Collects daily statistics for a car wash.
    Uses existing APIs from the codebase.
    
    Args:
        car_wash: Car wash document name
        date: Date in YYYY-MM-DD format
        
    Returns:
        Dictionary with report data or None if error
    """
    try:
        # Save original form_dict
        original_form_dict = getattr(frappe, 'form_dict', {})
        if hasattr(original_form_dict, 'copy'):
            original_form_dict = original_form_dict.copy()
        else:
            original_form_dict = dict(original_form_dict) if original_form_dict else {}
        
        # Set form_dict for API calls
        frappe.form_dict = {"car_wash": car_wash, "date": date}
        
        # Import statistics functions
        from car_wash_management.car_wash_management.doctype.car_wash_appointment.car_wash_statistics import get_statistics
        from car_wash_management.car_wash_management.doctype.car_wash_worker.car_wash_worker import get_worker_daily_stats
        from car_wash_management.car_wash_management.doctype.car_wash_service.car_wash_service import get_services_statistics
        
        # Get main statistics
        stats = get_statistics(car_wash=car_wash, date=date)
        
        # Get worker statistics
        worker_stats = get_worker_daily_stats()
        
        # Get service statistics
        service_stats_result = get_services_statistics()
        service_stats = service_stats_result.get("daily_stats", {}) if isinstance(service_stats_result, dict) else {}
        
        # Restore original form_dict
        frappe.form_dict = original_form_dict
        
        return {
            "date": date,
            "car_wash": car_wash,
            "stats": stats,
            "worker_stats": worker_stats,
            "service_stats": service_stats,
        }
        
    except Exception as e:
        frappe.log_error(
            f"Error generating daily report for {car_wash}: {frappe.get_traceback()}",
            "Generate Daily Report Error"
        )
        # Restore form_dict on error
        try:
            frappe.form_dict = original_form_dict
        except:
            pass
        return None


def format_telegram_message(report_data: dict, car_wash_name: str) -> str:
    """
    Formats the report data into a readable Telegram message with HTML formatting.
    
    Args:
        report_data: Dictionary with statistics data
        car_wash_name: Name of the car wash
        
    Returns:
        Formatted HTML message string
    """
    stats = report_data.get("stats", {})
    worker_stats = report_data.get("worker_stats", {})
    service_stats = report_data.get("service_stats", {})
    date = report_data.get("date", "")
    
    # Format date
    try:
        date_obj = getdate(date)
        formatted_date = date_obj.strftime("%d.%m.%Y")
    except:
        formatted_date = date
    
    # Build message
    message_parts = [
        f"📊 <b>Ежедневный отчет: {car_wash_name}</b>",
        f"📅 Дата: {formatted_date}",
        ""
    ]
    
    # Main statistics
    total_cars = stats.get('total_cars', 0)
    total_income = flt(stats.get('total_income', 0))
    
    message_parts.append(f"🚗 <b>Автомобилей:</b> {total_cars}")
    message_parts.append(f"💰 <b>Выручка:</b> {total_income:,.0f} ₸")
    
    if total_cars > 0:
        avg_check = total_income / total_cars
        message_parts.append(f"💵 <b>Средний чек:</b> {avg_check:,.0f} ₸")
    
    message_parts.append("")
    
    # Payment methods
    payment_methods = []
    cash_total = flt(stats.get('cash_payment', {}).get('total', 0))
    card_total = flt(stats.get('card_payment', {}).get('total', 0))
    kaspi_total = flt(stats.get('kaspi_payment', {}).get('total', 0))
    contract_total = flt(stats.get('contract_payment', {}).get('total', 0))
    
    if cash_total > 0:
        payment_methods.append(f"💵 Наличные: {cash_total:,.0f} ₸")
    if card_total > 0:
        payment_methods.append(f"💳 Карта: {card_total:,.0f} ₸")
    if kaspi_total > 0:
        payment_methods.append(f"📱 Kaspi: {kaspi_total:,.0f} ₸")
    if contract_total > 0:
        payment_methods.append(f"📄 Договор: {contract_total:,.0f} ₸")
    
    # Custom payment methods
    custom_payments = stats.get('custom_payments', {})
    if custom_payments:
        for method_name, method_data in custom_payments.items():
            method_total = flt(method_data.get('total', 0))
            if method_total > 0:
                payment_methods.append(f"🔹 {method_name}: {method_total:,.0f} ₸")
    
    if payment_methods:
        message_parts.append("<b>Способы оплаты:</b>")
        message_parts.extend(payment_methods)
        message_parts.append("")
    
    # Top workers (top 3)
    if worker_stats and isinstance(worker_stats, dict):
        message_parts.append("<b>👷 Топ работников:</b>")
        sorted_workers = sorted(
            worker_stats.items(),
            key=lambda x: x[1].get('total_cars', 0) if isinstance(x[1], dict) else 0,
            reverse=True
        )[:3]
        
        for idx, (worker_id, worker_data) in enumerate(sorted_workers, 1):
            if isinstance(worker_data, dict):
                worker_name = worker_data.get('worker_name', 'Unknown')
                cars = worker_data.get('total_cars', 0)
                amount = flt(worker_data.get('total_amount', 0))
                message_parts.append(f"{idx}. {worker_name}: {cars} авто, {amount:,.0f} ₸")
        
        if sorted_workers:
            message_parts.append("")
    
    # Top services (top 5)
    if service_stats and isinstance(service_stats, dict):
        message_parts.append("<b>🔧 Популярные услуги:</b>")
        sorted_services = sorted(
            service_stats.items(),
            key=lambda x: x[1].get('count', 0) if isinstance(x[1], dict) else 0,
            reverse=True
        )[:5]
        
        for idx, (service_name, service_data) in enumerate(sorted_services, 1):
            if isinstance(service_data, dict):
                count = service_data.get('count', 0)
                total = flt(service_data.get('total', 0))
                message_parts.append(f"{idx}. {service_name}: {count} раз, {total:,.0f} ₸")
    
    return "\n".join(message_parts)


def send_telegram_message(chat_id: str, message: str, parse_mode: str = "HTML") -> bool:
    """
    Sends a message to Telegram using Bot API.
    
    Args:
        chat_id: Telegram chat ID
        message: Message text
        parse_mode: Parse mode (HTML or Markdown)
        
    Returns:
        True if successful, False otherwise
    """
    # Get bot token from JWT Settings
    try:
        jwt_settings = frappe.get_single("JWT Settings")
        bot_token = jwt_settings.get("telegram_bot_token")
    except Exception as e:
        frappe.logger().error(f"[Telegram Daily Reports] Error getting JWT Settings: {str(e)}")
        bot_token = None
    
    if not bot_token:
        frappe.logger().error("[Telegram Daily Reports] Telegram bot token not configured in JWT Settings")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        if result.get("ok"):
            frappe.logger().info(f"[Telegram Daily Reports] Message sent to chat {chat_id}")
            return True
        else:
            error_desc = result.get('description', 'Unknown error')
            frappe.logger().error(f"[Telegram Daily Reports] Telegram API error: {error_desc}")
            return False
            
    except requests.exceptions.Timeout:
        frappe.logger().error("[Telegram Daily Reports] Request timeout when sending to Telegram")
        return False
    except requests.exceptions.RequestException as e:
        frappe.log_error(
            f"Failed to send Telegram message: {str(e)}",
            "Telegram Daily Reports"
        )
        return False
    except Exception as e:
        frappe.log_error(
            f"Unexpected error sending Telegram message: {frappe.get_traceback()}",
            "Telegram Daily Reports"
        )
        return False

