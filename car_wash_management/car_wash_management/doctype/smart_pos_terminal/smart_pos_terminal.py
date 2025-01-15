# Copyright (c) 2025, Rifat and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ....smartposapi import SmartPOSAPI
import requests

class SmartPOSTerminal(Document):
	pass


@frappe.whitelist()
def register_terminal(terminal_name, ip_address):
	settings = frappe.get_doc("Smart POS Settings")
	api = SmartPOSAPI(ip_address, settings.access_token)
	response = api.register_terminal(terminal_name)

	if response.get("statusCode") == 0:
		frappe.db.set_value("Smart POS Settings", None, "access_token",
							response['data']['accessToken'])
		frappe.db.set_value("Smart POS Settings", None, "refresh_token",
							response['data']['refreshToken'])
		frappe.db.set_value("Smart POS Settings", None, "expiration_date",
							response['data']['expirationDate'])
		frappe.db.commit()
		return "Terminal registered successfully"
	return response.get("errorText")


@frappe.whitelist()
def initiate_payment(amount, terminal_id):
	terminal = frappe.get_doc("Smart POS Terminal", terminal_id)
	settings = frappe.get_doc("Smart POS Settings")
	api = SmartPOSAPI(terminal.ip_address, settings.access_token)
	response = api.initiate_payment(amount)

	if response.get("statusCode") == 0:
		log = frappe.get_doc({
			"doctype": "Smart POS Terminal Transaction Log",
			"process_id": response['data']['processId'],
			"amount": amount,
			"status": "Pending",
			"timestamp": frappe.utils.now_datetime()
		})
		log.insert()
		frappe.db.commit()
		return "Payment initiated"
	return response.get("errorText")


@frappe.whitelist()
def check_transaction_status(process_id):
	settings = frappe.get_doc("Smart POS Settings")
	log = frappe.get_doc("Smart POS Terminal Transaction Log", {"process_id": process_id})
	api = SmartPOSAPI(log.ip_address, settings.access_token)
	response = api.get_transaction_status(process_id)

	if response.get("statusCode") == 0:
		frappe.db.set_value("Smart POS Terminal Transaction Log", {"process_id": process_id}, "status",
							response['data']['status'])
		frappe.db.commit()
		return response['data']
	return response.get("errorText")


@frappe.whitelist()
def update_token(refresh_token):
	settings = frappe.get_doc("Smart POS Settings")
	api = SmartPOSAPI(settings.default_ip_address, settings.access_token)
	response = api.update_token(refresh_token)

	if response.get("statusCode") == 0:
		frappe.db.set_value("Smart POS Settings", None, "access_token",
							response['data']['accessToken'])
		frappe.db.set_value("Smart POS Settings", None, "refresh_token",
							response['data']['refreshToken'])
		frappe.db.set_value("Smart POS Settings", None, "expiration_date",
							response['data']['expirationDate'])
		frappe.db.commit()
		return "Token updated successfully"
	return response.get("errorText")


@frappe.whitelist()
def test_connection(terminal_id):
	"""
	Test the connection to a Smart POS terminal and log the result in POS Connection Test.
	:param terminal_id: ID of the terminal to test.
	:return: Connection status and device details if successful.
	"""
	try:
		# Fetch terminal details
		terminal = frappe.get_doc("Smart POS Terminal", terminal_id)

		if not terminal.ip_address:
			return {"status": "fail", "message": "IP address not configured for this terminal"}

		# Access settings for token
		settings = frappe.get_doc("Smart POS Settings")
		if not settings.access_token:
			return {"status": "fail", "message": "Access token not configured"}

		# Test connection to Smart POS
		response = requests.get(
			f"https://{terminal.ip_address}:8080/v2/deviceinfo",
			headers={"accesstoken": settings.access_token},
			timeout=5
		)

		# Parse and log response
		if response.status_code == 200:
			data = response.json().get("data", {})
			log = frappe.get_doc({
				"doctype": "Smart POS Connection Test",
				"terminal_id": terminal.name,
				"test_date": frappe.utils.now(),
				"connection_status": "Success",
				"error_message": None
			})
			log.insert()
			frappe.db.commit()
			return {
				"status": "success",
				"message": "Connection successful",
				"device_info": {
					"terminal_id": data.get("terminalId"),
					"serial_number": data.get("serialNum"),
					"pos_number": data.get("posNum")
				}
			}
		else:
			error_message = f"Unexpected response: {response.status_code} - {response.text}"
			frappe.get_doc({
				"doctype": "Smart POS Connection Test",
				"terminal_id": terminal.name,
				"test_date": frappe.utils.now(),
				"connection_status": "Failed",
				"error_message": error_message
			}).insert()
			frappe.db.commit()
			return {"status": "fail", "message": error_message}
	except requests.exceptions.RequestException as e:
		frappe.get_doc({
			"doctype": "Smart POS Connection Test",
			"terminal_id": terminal.name,
			"test_date": frappe.utils.now(),
			"connection_status": "Failed",
			"error_message": str(e)
		}).insert()
		frappe.db.commit()
		return {"status": "fail", "message": f"Connection error: {str(e)}"}
	except Exception as e:
		frappe.get_doc({
			"doctype": "Smart POS Connection Test",
			"terminal_id": terminal.name,
			"test_date": frappe.utils.now(),
			"connection_status": "Failed",
			"error_message": str(e)
		}).insert()
		frappe.db.commit()
		return {"status": "fail", "message": f"An unexpected error occurred: {str(e)}"}

@frappe.whitelist()
def get_connection_history(terminal_id):
    """
    Fetch connection test history for a specific terminal.
    :param terminal_id: ID of the terminal.
    :return: List of connection test logs.
    """
    history = frappe.get_all(
        "Smart POS Connection Test",
        filters={"terminal_id": terminal_id},
        fields=["test_date", "connection_status", "error_message"],
        order_by="test_date desc"
    )
    return history

@frappe.whitelist()
def get_transactions(terminal_id):
    """
    Fetch all transactions for a specific terminal.
    :param terminal_id: ID of the terminal.
    :return: List of transactions.
    """
    transactions = frappe.get_all(
        "Smart POS Terminal Transaction Log",
        filters={"terminal_id": terminal_id},
        fields=["process_id", "amount", "status", "timestamp", "transaction_id", "payment_method"],
        order_by="timestamp desc"
    )
    return transactions

@frappe.whitelist()
def initiate_refund(transaction_id, refund_amount):
    """
    Initiate a refund for a specific transaction.
    :param transaction_id: The ID of the transaction to refund.
    :param refund_amount: The amount to refund.
    :return: Refund process status.
    """
    try:
        # Fetch transaction details
        transaction = frappe.get_doc("Smart POS Terminal Transaction Log", {"transaction_id": transaction_id})
        if transaction.status != "Success":
            return {"status": "fail", "message": "Only successful transactions can be refunded"}

        # Access settings for token
        settings = frappe.get_doc("Smart POS Settings")
        api = SmartPOSAPI(transaction.terminal_id, settings.access_token)

        # Initiate refund via API
        response = api.initiate_refund(transaction.transaction_id, refund_amount)
        if response.get("statusCode") == 0:
            return {
                "status": "success",
                "message": "Refund initiated successfully",
                "process_id": response['data']['processId']
            }
        return {"status": "fail", "message": response.get("errorText")}
    except Exception as e:
        return {"status": "fail", "message": f"An unexpected error occurred: {str(e)}"}


@frappe.whitelist()
def refresh_tokens():
	"""
	Refresh access tokens periodically to ensure uninterrupted access.
	:return: Status of token refresh.
	"""
	try:
		settings = frappe.get_doc("Smart POS Settings")
		if not settings.refresh_token:
			return {"status": "fail", "message": "Refresh token not configured"}

		api = SmartPOSAPI(settings.default_ip_address, settings.access_token)
		response = api.update_token(settings.refresh_token)
		if response.get("statusCode") == 0:
			frappe.db.set_value("Smart POS Settings", None, "access_token",
								response['data']['accessToken'])
			frappe.db.set_value("Smart POS Settings", None, "refresh_token",
								response['data']['refreshToken'])
			frappe.db.set_value("Smart POS Settings", None, "expiration_date",
								response['data']['expirationDate'])
			frappe.db.commit()
			return {"status": "success", "message": "Token refreshed successfully"}
		return {"status": "fail", "message": response.get("errorText")}
	except Exception as e:
		return {"status": "fail", "message": f"An unexpected error occurred: {str(e)}"}


@frappe.whitelist()
def update_transaction_status(process_id):
    try:
        transaction = frappe.get_doc("Smart POS Terminal Transaction Log", {"process_id": process_id})
        terminal = frappe.get_doc("Smart POS Terminal", transaction.terminal_id)
        settings = frappe.get_doc("Smart POS Settings")
        api = SmartPOSAPI(terminal.ip_address, settings.access_token)

        # Check transaction status
        status_response = api.get_transaction_status(process_id)
        if status_response.get("statusCode") == 0:
            transaction.status = status_response["data"].get("status", "Unknown")
            transaction.transaction_id = status_response["data"].get("transactionId")
            transaction.save()

            # Actualize the transaction if it's successful
            if transaction.status == "Success":
                actualize_response = api.actualize(process_id)
                if actualize_response.get("statusCode") == 0:
                    transaction.status = "Finalized"
                    transaction.save()

            frappe.db.commit()
            return {
                "status": "success",
                "message": "Transaction status updated and finalized successfully",
                "updated_status": transaction.status,
                "transaction_id": transaction.transaction_id
            }
        else:
            return {"status": "fail", "message": status_response.get("errorText", "Failed to fetch transaction status")}
    except Exception as e:
        return {"status": "fail", "message": f"An unexpected error occurred: {str(e)}"}


@frappe.whitelist()
def get_device_info(terminal_id):
	"""
	Fetch device information for a specific Smart POS terminal.
	:param terminal_id: ID of the terminal to fetch device info.
	:return: Device information if successful, or error message.
	"""
	try:
		# Fetch terminal details
		terminal = frappe.get_doc("Smart POS Terminal", terminal_id)
		if not terminal:
			return {"status": "fail", "message": f"Terminal with ID {terminal_id} not found"}

		if not terminal.ip_address:
			return {"status": "fail", "message": "Terminal does not have an IP address configured"}

		# Fetch Smart POS settings
		settings = frappe.get_doc("Smart POS Settings")
		if not settings.access_token:
			return {"status": "fail", "message": "Access token is not configured"}

		# Create API client
		api = SmartPOSAPI(terminal.ip_address, settings.access_token)

		# Fetch device information
		response = api.device_info()
		if response.get("statusCode") == 0:
			# Save device info in terminal record
			terminal.serial_number = response["data"].get("serialNum")
			terminal.terminal_id = response["data"].get("terminalId")
			terminal.pos_number = response["data"].get("posNum")
			terminal.save()
			frappe.db.commit()

			return {
				"status": "success",
				"message": "Device information retrieved successfully",
				"device_info": {
					"terminal_id": terminal.terminal_id,
					"serial_number": terminal.serial_number,
					"pos_number": terminal.pos_number
				}
			}
		else:
			return {"status": "fail",
					"message": response.get("errorText", "Failed to fetch device info")}
	except Exception as e:
		frappe.log_error(f"Error fetching device info for terminal ID {terminal_id}: {str(e)}",
						 "Device Info Error")
		return {"status": "fail", "message": f"An unexpected error occurred: {str(e)}"}
