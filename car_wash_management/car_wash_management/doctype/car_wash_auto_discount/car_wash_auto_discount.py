# Copyright (c) 2024, Rifat Dzhumagulov and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, getdate, flt


class Carwashautodiscount(Document):
    def validate(self):
        """Validate auto discount settings"""
        self.validate_dates()
        self.validate_discount_settings()
        # conditions are expressed via rules only now

    def validate_dates(self):
        """Validate date settings"""
        if self.valid_from and self.valid_to:
            if getdate(self.valid_from) > getdate(self.valid_to):
                frappe.throw("Дата начала не может быть позже даты окончания")

    def validate_discount_settings(self):
        """Validate discount type and value"""
        if self.discount_type == "Percentage" and self.discount_value > 100:
            frappe.throw("Процентная скидка не может быть больше 100%")

        if self.discount_value <= 0:
            frappe.throw("Размер скидки должен быть больше 0")

    # single-field condition validation removed (rules-only)

    def is_valid_for_date(self, check_date=None):
        """Check if discount is valid for given date"""
        if not check_date:
            check_date = now_datetime().date()

        check_date = getdate(check_date)

        if self.valid_from and check_date < getdate(self.valid_from):
            return False

        if self.valid_to and check_date > getdate(self.valid_to):
            return False

        return True

    def is_condition_met(self, customer_stats, services=None):
        """
        Check if customer meets the discount condition

        Args:
            customer_stats: Stats from car_wash_client.get_statistics()
            services: List of services in current booking (for service-specific conditions)
        """
        if not customer_stats or not customer_stats.get("periods"):
            print("customer_stats is not valid")
            return False

        print("customer_stats is valid")

        # Rules-only evaluation
        return self._evaluate_rules(customer_stats, services)

    def _evaluate_rules(self, customer_stats, services=None):
        """Evaluate multiple rules with AND/OR logic"""
        logic = (self.rules_logic or "ALL (AND)").strip().upper()
        results = []
        print("rules", self.rules)
        for rule in self.rules:
            results.append(self._evaluate_single_rule(rule, customer_stats, services))
        if not results:
            return False
        if logic.startswith("ALL"):
            return all(results)
        return any(results)

    def _evaluate_single_rule(self, rule, customer_stats, services=None):
        """Evaluate a single rule row"""
        periods = customer_stats.get("periods", {})
        rule_type = (rule.rule_type or "").strip()
        operator = (rule.operator or ">=").strip()
        period_key = (rule.period or "all_time").strip() or "all_time"
        period_stats = periods.get(period_key, {})

        print("rule", rule)
        print("rule_type", rule_type)
        print("operator", operator)
        print("period_key", period_key)
        print("period_stats", period_stats)

        # Nth Order rule (every Nth order)
        if rule_type == "Nth Order":
            all_time = periods.get("all_time", {})
            next_order_no = int(all_time.get("total_appointments", 0) or 0) + 1
            step = int(rule.nth_step or 0)
            offset = int(rule.nth_offset or 0)
            if step <= 0:
                return False
            return ((next_order_no - offset) % step) == 0

        # Map rule types to values
        if rule_type == "Total Orders Count":
            actual = period_stats.get("total_appointments", 0)
        elif rule_type == "Paid Orders Count":
            actual = period_stats.get("paid_appointments", 0)
        elif rule_type == "Total Spent Amount":
            actual = period_stats.get("spent_total", 0.0)
        elif rule_type == "Unique Cars Count":
            actual = period_stats.get("unique_cars", 0)
        elif rule_type == "Average Ticket Amount":
            actual = period_stats.get("avg_ticket", 0.0)
        elif rule_type == "First Time Customer":
            all_time_stats = periods.get("all_time", {})
            period_paid = period_stats.get("paid_appointments", 0) or 0
            all_time_paid = all_time_stats.get("paid_appointments", 0) or 0
            return all_time_paid == 0 or all_time_paid == 1
        elif rule_type == "Last Visit Days Ago":
            last_visit = period_stats.get("last_visit_on")
            if not last_visit:
                return False
            actual = (now_datetime().date() - getdate(last_visit)).days
        elif rule_type == "Service Usage Count":
            # If rule has own services list, use it; otherwise fallback to document-level target_services
            if getattr(rule, "services", None):
                target_services = [row.service for row in rule.services]
            else:
                target_services = [row.service for row in (self.target_services or [])]
            actual = self._get_service_usage_count(period_stats.get("top_services", []), target_services)
        else:
            return False

        target = flt(rule.value or 0)
        return self._check_operator(operator, actual, target)

    def _check_operator(self, operator, actual_value, target_value):
        """Generic operator check for rule rows"""
        actual_value = flt(actual_value)
        target_value = flt(target_value)
        if operator == ">=":
            return actual_value >= target_value
        if operator == ">":
            return actual_value > target_value
        if operator == "=":
            return actual_value == target_value
        if operator == "<":
            return actual_value < target_value
        if operator == "<=":
            return actual_value <= target_value
        return False

    def _get_service_usage_count(self, top_services, target_service_names=None):
        """Get usage count for target services"""
        if not target_service_names:
            if not self.target_services:
                return 0
            target_service_names = [row.service for row in self.target_services]
        total_count = 0

        for service_stat in top_services:
            if service_stat.get("service") in target_service_names:
                total_count += service_stat.get("count", 0)

        return total_count

    def _check_condition_operator(self, actual_value, target_value):
        """Check condition based on operator"""
        actual_value = flt(actual_value)
        target_value = flt(target_value)

        if self.condition_operator == ">=":
            return actual_value >= target_value
        elif self.condition_operator == ">":
            return actual_value > target_value
        elif self.condition_operator == "=":
            return actual_value == target_value
        elif self.condition_operator == "<":
            return actual_value < target_value
        elif self.condition_operator == "<=":
            return actual_value <= target_value

        return False

    def is_applicable_to_services(self, services):
        """Check if discount applies to given services"""
        if not self.applicable_services:
            # If no specific services defined, applies to all
            return True

        applicable_service_names = [row.service for row in self.applicable_services]

        # Check if any of the booking services match applicable services
        for service in services:
            service_name = service if isinstance(service, str) else service.get("service_id")
            if service_name in applicable_service_names:
                return True

        return False

    def calculate_discount_amount(self, services_total):
        """Calculate discount amount based on discount type and value"""
        if self.discount_type == "Percentage":
            return (services_total * self.discount_value) / 100
        else:  # Fixed Amount
            return min(self.discount_value, services_total)  # Don't exceed total amount


@frappe.whitelist()
def get_auto_discounts_with_rules(car_wash: str, include_inactive: int = 1):
    """
    Return all auto discounts for a car wash including child tables (rules and services).

    Args:
        car_wash: Car wash ID
        include_inactive: 1 to include inactive discounts, 0 to include only active

    Returns:
        { status, count, discounts: [...] }
    """
    filters = {
        "car_wash": car_wash,
        "is_deleted": 0,
    }
    if not int(include_inactive or 0):
        filters["is_active"] = 1

    rows = frappe.get_all(
        "Car wash auto discount",
        filters=filters,
        order_by="priority asc",
        fields=["name"]
    )

    discounts = []
    for row in rows:
        doc = frappe.get_doc("Car wash auto discount", row.name)

        # Flatten child tables
        rules = []
        try:
            for r in (doc.rules or []):
                rules.append({
                    "rule_type": r.rule_type,
                    "operator": r.operator,
                    "value": r.value,
                    "period": r.period,
                    "nth_step": r.nth_step,
                    "nth_offset": r.nth_offset,
                    "services": [s.service for s in (getattr(r, "services", []) or [])],
                })
        except Exception:
            rules = []

        discounts.append({
            "name": doc.name,
            "name_title": doc.name_title,
            "description": doc.description,
            "discount_type": doc.discount_type,
            "discount_value": doc.discount_value,
            "minimum_order_amount": doc.minimum_order_amount,
            "waive_queue_commission": doc.waive_queue_commission,
            "rules_logic": doc.rules_logic,
            "priority": doc.priority,
            "valid_from": doc.valid_from,
            "valid_to": doc.valid_to,
            "usage_limit_per_customer": doc.usage_limit_per_customer,
            "can_combine_with_promocodes": doc.can_combine_with_promocodes,
            "can_combine_with_other_auto_discounts": doc.can_combine_with_other_auto_discounts,
            "is_active": doc.is_active,
            "target_services": [s.service for s in (doc.target_services or [])],
            "applicable_services": [s.service for s in (doc.applicable_services or [])],
            "rules": rules,
        })

    return {
        "status": "success",
        "count": len(discounts),
        "discounts": discounts,
    }
