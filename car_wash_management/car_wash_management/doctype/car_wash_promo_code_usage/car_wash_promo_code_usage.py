# car_wash_promo_code_usage.py

import frappe
from frappe import _
from typing import Dict, List, Any

# Copyright (c) 2025, Rifat and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class Carwashpromocodeusage(Document):
	pass

@frappe.whitelist()
def get_promo_code_usage_history(promo_code: str, limit: int = 500) -> Dict[str, Any]:
    """
    Get usage history for a specific promo code with detailed information.
    
    Args:
        promo_code: Name/ID of the promo code document
        limit: Maximum number of records to return (default 500)
    
    Returns:
        Dict with message containing list of usage records
    """
    try:
        # Validate promo code exists
        if not frappe.db.exists("Car wash promo code", promo_code):
            frappe.throw(_("Promo code not found"))
        
        # Get usage history with joins for additional information
        usage_records = frappe.db.sql("""
            SELECT 
                pcu.name,
                pcu.usage_date,
                pcu.promo_type,
                pcu.service_discount_amount,
                pcu.commission_waived_amount,
                pcu.total_discount_amount,
                pcu.original_services_total,
                pcu.original_commission,
                pcu.final_services_total,
                pcu.final_commission,
                pcu.user,
                pcu.mobile_booking_attempt,
                user.full_name as user_name,
                user.phone as user_phone,
                promo.code as promo_code,
                promo.title as promo_title
            FROM 
                `tabCar wash promo code usage` pcu
            LEFT JOIN 
                `tabMobile App User` user ON pcu.user = user.name
            LEFT JOIN 
                `tabCar wash promo code` promo ON pcu.promo_code = promo.name
            WHERE 
                pcu.promo_code = %s
            ORDER BY 
                pcu.usage_date DESC
            LIMIT %s
        """, (promo_code, int(limit)), as_dict=True)
        
        # Format dates and add calculated fields
        for record in usage_records:
            # Format usage_date for better display
            if record.get('usage_date'):
                record['formatted_date'] = frappe.format_value(
                    record['usage_date'], 'Datetime'
                )
            
            # Calculate savings percentage if possible
            original_total = (record.get('original_services_total', 0) + 
                            record.get('original_commission', 0))
            if original_total > 0:
                savings_percent = (record.get('total_discount_amount', 0) / original_total) * 100
                record['savings_percentage'] = round(savings_percent, 1)
            else:
                record['savings_percentage'] = 0
        
        return usage_records
        
    except Exception as e:
        frappe.log_error(f"Error getting promo code usage history: {str(e)}", "Promo Code Usage History")
        frappe.throw(_("Failed to get promo code usage history"))


@frappe.whitelist()
def get_all_promo_code_usage_stats(car_wash: str) -> Dict[str, Any]:
    """
    Get aggregated statistics for all promo code usage for a car wash.
    
    Args:
        car_wash: Name/ID of the car wash
    
    Returns:
        Dict with aggregated statistics
    """
    try:
        # Get aggregated stats
        stats = frappe.db.sql("""
            SELECT 
                COUNT(*) as total_usages,
                SUM(pcu.total_discount_amount) as total_savings,
                SUM(pcu.service_discount_amount) as total_service_discounts,
                SUM(pcu.commission_waived_amount) as total_commission_waived,
                COUNT(DISTINCT pcu.user) as unique_users,
                COUNT(DISTINCT pcu.promo_code) as promo_codes_used
            FROM 
                `tabCar wash promo code usage` pcu
            JOIN 
                `tabCar wash promo code` promo ON pcu.promo_code = promo.name
            WHERE 
                promo.car_wash = %s
        """, (car_wash,), as_dict=True)
        
        # Get top performing promo codes
        top_promos = frappe.db.sql("""
            SELECT 
                promo.code,
                promo.title,
                COUNT(*) as usage_count,
                SUM(pcu.total_discount_amount) as total_savings
            FROM 
                `tabCar wash promo code usage` pcu
            JOIN 
                `tabCar wash promo code` promo ON pcu.promo_code = promo.name
            WHERE 
                promo.car_wash = %s
            GROUP BY 
                pcu.promo_code
            ORDER BY 
                usage_count DESC
            LIMIT 10
        """, (car_wash,), as_dict=True)
        
        # Get usage by type
        usage_by_type = frappe.db.sql("""
            SELECT 
                pcu.promo_type,
                COUNT(*) as usage_count,
                SUM(pcu.total_discount_amount) as total_savings
            FROM 
                `tabCar wash promo code usage` pcu
            JOIN 
                `tabCar wash promo code` promo ON pcu.promo_code = promo.name
            WHERE 
                promo.car_wash = %s
            GROUP BY 
                pcu.promo_type
            ORDER BY 
                usage_count DESC
        """, (car_wash,), as_dict=True)
        
        return {
            "overall_stats": stats[0] if stats else {},
            "top_promo_codes": top_promos,
            "usage_by_type": usage_by_type
        }
        
    except Exception as e:
        frappe.log_error(f"Error getting promo code stats: {str(e)}", "Promo Code Stats")
        frappe.throw(_("Failed to get promo code statistics"))


@frappe.whitelist()
def get_recent_promo_code_usages(car_wash: str, limit: int = 50) -> Dict[str, Any]:
    """
    Get recent promo code usages across all promo codes for a car wash.
    
    Args:
        car_wash: Name/ID of the car wash
        limit: Maximum number of records to return (default 50)
    
    Returns:
        Dict with message containing list of recent usage records
    """
    try:
        # Get recent usage records
        recent_usages = frappe.db.sql("""
            SELECT 
                pcu.name,
                pcu.usage_date,
                pcu.promo_type,
                pcu.total_discount_amount,
                promo.code as promo_code,
                promo.title as promo_title,
                user.full_name as user_name,
                pcu.mobile_booking_attempt
            FROM 
                `tabCar wash promo code usage` pcu
            JOIN 
                `tabCar wash promo code` promo ON pcu.promo_code = promo.name
            LEFT JOIN 
                `tabMobile App User` user ON pcu.user = user.name
            WHERE 
                promo.car_wash = %s
            ORDER BY 
                pcu.usage_date DESC
            LIMIT %s
        """, (car_wash, int(limit)), as_dict=True)
        
        return recent_usages
        
    except Exception as e:
        frappe.log_error(f"Error getting recent promo code usages: {str(e)}", "Recent Promo Code Usages")
        frappe.throw(_("Failed to get recent promo code usages"))
