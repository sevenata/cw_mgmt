import requests

class SmartPOSAPI:
    def __init__(self, ip_address, token):
        """
        Initialize the SmartPOSAPI with terminal IP and access token.
        :param ip_address: IP address of the Smart POS terminal.
        :param token: Access token for API authentication.
        """
        self.base_url = f"https://{ip_address}:8080/v2"
        self.token = token

    def _headers(self):
        """
        Return the headers required for API requests.
        """
        return {'accesstoken': self.token}

    def register_terminal(self, terminal_name):
        url = f"{self.base_url}/register"
        params = {'name': terminal_name}
        response = requests.get(url, params=params, headers=self._headers())
        return response.json()

    def update_token(self, refresh_token):
        url = f"{self.base_url}/revoke"
        params = {'refreshToken': refresh_token}
        response = requests.get(url, params=params, headers=self._headers())
        return response.json()

    def initiate_payment(self, amount, own_cheque=False):
        url = f"{self.base_url}/payment"
        params = {'amount': amount, 'owncheque': own_cheque}
        response = requests.get(url, params=params, headers=self._headers())
        return response.json()

    def get_transaction_status(self, process_id):
        url = f"{self.base_url}/status"
        params = {'processId': process_id}
        response = requests.get(url, params=params, headers=self._headers())
        return response.json()

    def actualize(self, process_id):
        url = f"{self.base_url}/actualize"
        params = {'processId': process_id}
        response = requests.get(url, params=params, headers=self._headers())
        if response.status_code == 200:
            return response.json()
        else:
            return {"statusCode": response.status_code, "errorText": response.text}

    def device_info(self):
        url = f"{self.base_url}/deviceinfo"
        response = requests.get(url, headers=self._headers())
        if response.status_code == 200:
            return response.json()
        else:
            return {"statusCode": response.status_code, "errorText": response.text}

    def initiate_refund(self, transaction_id, refund_amount):
        """
        Initiate a refund for a specific transaction.
        :param transaction_id: ID of the transaction to refund.
        :param refund_amount: Amount to refund.
        :return: API response.
        """
        url = f"{self.base_url}/refund"
        params = {
            'transactionId': transaction_id,
            'amount': refund_amount
        }
        response = requests.get(url, params=params, headers=self._headers())
        if response.status_code == 200:
            return response.json()
        else:
            return {"statusCode": response.status_code, "errorText": response.text}
