import os
import pytz
from tzlocal import get_localzone

TIMEZONE = os.environ.get("SCRAPER_TIMEZONE", "UTC")
if TIMEZONE:
    tz = pytz.timezone(TIMEZONE)
else:
    tz = get_localzone()

# --- Proxy configuration ---
proxy_host = "brd.superproxy.io"
proxy_port = 33335
proxy_user = "brd-customer-hl_bfc03546-zone-datacenter_proxy2"
proxy_pass = "ye6bg16kmm2m"

proxies = {
    "http": f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}",
    "https": f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}",
}

headers = {
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

url = "https://www.ikyu.com/graphql?lang=ja-JP"

# Use the hotel_detail/ikyu_all_hotel.json as the input file for hotel data
input_ids_file = "../hotel_detail/ikyu_all_hotel.json"
final_file = "ikyu_all_hotels_final.json" 