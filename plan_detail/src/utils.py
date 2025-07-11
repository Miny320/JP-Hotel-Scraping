from datetime import datetime
import hashlib
import time
import requests
from .config import tz, url, headers, proxies

def get_now():
    return datetime.now(tz)

def get_last_updated_at():
    return get_now().strftime("%Y-%m-%d %H:%M:%S")

def get_process_hash_id():
    return hashlib.md5(str(tz).encode()).hexdigest()

def infinite_retry_post(json_payload):
    """
    Keeps retrying the request forever until it succeeds. Never skips any request.
    Logs a warning every 10 consecutive failures.
    """
    wait_time = 5
    retries = 0
    while True:
        try:
            response = requests.post(url, headers=headers, proxies=proxies, json=json_payload, timeout=30)
            response.raise_for_status()
            return response
        except Exception as e:
            retries += 1
            print(f"Request failed with error: {e}. Retrying in {wait_time} seconds... (Attempt {retries})")
            if retries % 10 == 0:
                print(f"Warning: {retries} consecutive failures for this request. Still retrying...")
            time.sleep(wait_time)
            wait_time = min(wait_time * 2, 60) 