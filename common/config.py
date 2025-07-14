import os
import pytz
from tzlocal import get_localzone

TIMEZONE = os.environ.get("SCRAPER_TIMEZONE", "UTC")
if TIMEZONE:
    TZ = pytz.timezone(TIMEZONE)
else:
    TZ = get_localzone()

PROXY_HOST = "brd.superproxy.io"
PROXY_PORT = 33335
PROXY_USER = "brd-customer-hl_bfc03546-zone-datacenter_proxy2"
PROXY_PASS = "ye6bg16kmm2m"

PROXIES = {
    "http": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}",
    "https": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}",
}

HEADERS = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,af;q=0.7",
    "content-type": "application/json",
    "origin": "https://www.ikyu.com",
    "referer": "https://www.ikyu.com/",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "cookie": ""
}

URL = "https://www.ikyu.com/graphql?lang=ja-JP"

# File paths
HOTEL_JSON = "hotel_detail/ikyu_all_hotel.json"
PLAN_FINAL_FILE = "plan_detail/ikyu_all_hotels.jsonl" 