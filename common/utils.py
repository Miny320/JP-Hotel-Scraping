import hashlib
import re
import time
from datetime import datetime
import requests
from .config import TZ, URL, HEADERS, PROXIES

def get_now():
    """Get the current datetime in the configured timezone."""
    return datetime.now(TZ)

def get_last_updated_at() -> str:
    """Get the current time in the configured timezone as a string."""
    return get_now().strftime("%Y-%m-%d %H:%M:%S")

def get_process_hash_id() -> str:
    """Get a hash ID for the current process based on timezone."""
    return hashlib.md5(str(TZ).encode()).hexdigest()

def to_e164_jp_phone(phone: str) -> str:
    """Convert a Japanese phone number to E.164 format."""
    if not phone:
        return phone
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('0'):
        digits = digits[1:]
    return '+81' + digits

def infinite_retry_post(json_payload):
    """
    Keeps retrying the request forever until it succeeds. Never skips any request.
    Logs a warning every 10 consecutive failures.
    """
    wait_time = 5
    retries = 0
    while True:
        try:
            response = requests.post(URL, headers=HEADERS, proxies=PROXIES, json=json_payload, timeout=30)
            response.raise_for_status()
            return response
        except Exception as e:
            retries += 1
            print(f"Request failed with error: {e}. Retrying in {wait_time} seconds... (Attempt {retries})")
            if retries % 10 == 0:
                print(f"Warning: {retries} consecutive failures for this request. Still retrying...")
            time.sleep(wait_time)
            wait_time = min(wait_time * 2, 60) 