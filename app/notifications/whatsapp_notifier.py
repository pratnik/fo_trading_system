"""
WhatsApp notification client using Gupshup API
- Trade fills, error alerts, exits, health check failures, etc
"""
import requests
import logging

logger = logging.getLogger("whatsapp_notifier")

class WhatsAppNotifier:
    def __init__(self, api_key, app_name, to_number):
        self.api_key = api_key
        self.app_name = app_name
        self.to_number = to_number

    def send_message(self, text: str):
        url = "https://api.gupshup.io/sm/api/v1/msg"
        payload = {
            "channel": "whatsapp",
            "source": self.app_name,
            "destination": self.to_number,
            "message": text
        }
        headers = {"apikey": self.api_key}
        try:
            resp = requests.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                logger.info(f"WhatsApp sent: {text}")
                return True
            logger.error(f"Whatsapp error: {resp.text}")
            return False
        except Exception as e:
            logger.error(f"WhatsApp send failed: {e}")
            return False
