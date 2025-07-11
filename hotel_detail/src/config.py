import os
import pytz

# === Proxy configuration ===
PROXY_HOST = "brd.superproxy.io"
PROXY_PORT = 33335
PROXY_USER = "brd-customer-hl_bfc03546-zone-datacenter_proxy2"
PROXY_PASS = "ye6bg16kmm2m"

PROXIES = {
    "http": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}",
    "https": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}",
}

HEADERS = {
    "content-type": "application/json",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "referer": "https://www.ikyu.com/search?accommodation_types=RESORT_HOTEL,HOTEL,INN,BUSINESS&adc=1&lc=1&ppc=2&rc=1&si=6",
}

URL = "https://www.ikyu.com/graphql?lang=ja-JP"
JSON_FILENAME = "ikyu_all_hotel.json"

TIMEZONE = os.environ.get("SCRAPER_TIMEZONE", "UTC")
tz = pytz.timezone(TIMEZONE) 