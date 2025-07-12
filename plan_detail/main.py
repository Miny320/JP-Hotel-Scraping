import requests
import json
from datetime import datetime, timedelta
import time
import os
import sys
import hashlib
import pytz
from tzlocal import get_localzone
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from src.hotel_fetcher import run_all_hotels

# --- Timezone handling: Use env or fall back to local time zone ---
TIMEZONE = os.environ.get("SCRAPER_TIMEZONE", "Europe/Kyiv")
if TIMEZONE:
    tz = pytz.timezone(TIMEZONE)
else:
    tz = get_localzone()  # Uses your computer's local timezone

def get_now():
    return datetime.now(tz)

def get_last_updated_at():
    return get_now().strftime("%Y-%m-%d %H:%M:%S")

def get_process_hash_id():
    return hashlib.md5(str(tz).encode()).hexdigest()

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

input_ids_file = "ikyu_all_hotel_ids.jsonl"
final_file = "ikyu_all_hotels_final.json"

# For monitoring concurrent hotels
running_hotels = set()
lock = threading.Lock()
results_lock = threading.Lock()
all_hotels = []

def infinite_retry_post(json_payload):
    wait_time = 5
    while True:
        try:
            response = requests.post(url, headers=headers, proxies=proxies, json=json_payload, timeout=30)
            response.raise_for_status()
            return response
        except Exception as e:
            print(f"Request failed with error: {e}. Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
            wait_time = min(wait_time * 2, 60)

def read_hotel_ids():
    hotel_ids = []
    with open(input_ids_file, "r", encoding="utf-8") as f:
        hotels = json.load(f)
        for obj in hotels:
            hotel_ids.append(obj["hotel_id"])
    return hotel_ids

def meal_code_to_flags(meal_code):
    mapping = {
        "000": (False, False, False),
        "001": (True,  False, False),
        "002": (False, False, True),
        "003": (True,  False, True),
        "004": (True,  True,  False),
        "005": (False, True,  False),
        "006": (True,  True,  True),
        "007": (False, True,  True),
    }
    return mapping.get(meal_code, (False, False, False))

def fetch_plans(accommodation_id, adult_count):
    all_plan_edges = []
    plans_first = 10
    plans_offset = 0
    while True:
        payload_plans = {
            "query": """
            query PlansAndRooms($accommodationId: AccommodationIdScalar!, $plansInput: SearchPlansInput! = {}, $plansFirst: Int!, $plansOffset: Int!) {
              accommodation(accommodationId: $accommodationId) {
                searchPlans2(input: $plansInput, first: $plansFirst, offset: $plansOffset) {
                  plans {
                    edges {
                      node {
                        planId
                        name
                        meal { code }
                      }
                    }
                    pageInfo {
                      hasNextPage
                    }
                  }
                }
              }
            }
            """,
            "variables": {
                "accommodationId": accommodation_id,
                "plansInput": {
                    "discount": True,
                    "lodgingCount": 1,
                    "peopleCount": adult_count,
                    "roomCount": 1,
                    "searchType": "1",
                    "sortItem": "1",
                    "sortOrder": "1",
                    "currency": "JPY",
                    "preferBookable": True
                },
                "plansFirst": plans_first,
                "plansOffset": plans_offset
            },
            "operationName": "PlansAndRooms"
        }
        response_plans = infinite_retry_post(payload_plans)
        plans_data = response_plans.json()
        plan_edges = plans_data.get('data', {}).get('accommodation', {}).get('searchPlans2', {}).get('plans', {}).get('edges', [])
        all_plan_edges.extend(plan_edges)
        page_info = plans_data.get('data', {}).get('accommodation', {}).get('searchPlans2', {}).get('plans', {}).get('pageInfo', {})
        has_next_page = page_info.get('hasNextPage', False)
        if not has_next_page or len(plan_edges) == 0:
            break
        plans_offset += plans_first
    return all_plan_edges

def fetch_rooms(accommodation_id, plan_id, adult_count):
    payload_roomlist = {
        "query": """
        query PlanList($accommodationId: AccommodationIdScalar!, $planId: PlanIdScalar!, $planAmountsInput: PlanAmountInput! = {sortItem: "1", sortOrder: "1"}, $first: Int! = 99, $offset: Int! = 0) {
          accommodation(accommodationId: $accommodationId) {
            plan(planId: $planId) {
              amounts(input: $planAmountsInput, first: $first, offset: $offset) {
                edges {
                  node {
                    room {
                      roomId
                      name
                    }
                  }
                }
              }
            }
          }
        }
        """,
        "variables": {
            "accommodationId": accommodation_id,
            "planId": plan_id,
            "planAmountsInput": {
                "discount": True,
                "lodgingCount": 1,
                "peopleCount": adult_count,
                "roomCount": 1,
                "searchType": "1",
                "sortItem": "1",
                "sortOrder": "1",
                "currency": "JPY"
            },
            "first": 99,
            "offset": 0
        },
        "operationName": "PlanList"
    }
    response_roomlist = infinite_retry_post(payload_roomlist)
    roomlist_data = response_roomlist.json()
    room_edges = roomlist_data.get('data', {}).get('accommodation', {}).get('plan', {}).get('amounts', {}).get('edges', [])
    return room_edges

def fetch_room_and_calendar(args):
    (accommodation_id, plan_id, plan_name, meal_code, breakfast, lunch, dinner,
     room_edge, now_date, limit_date, adult_count) = args

    node = room_edge.get('node', {})
    room = node.get('room', {})
    room_id = room.get("roomId")
    if not room_id:
        print("          Skipping room with missing roomId")
        return None

    plan_obj = {
        "plan_id": plan_id,
        "room_code": room_id,
        "checked_adult_count": adult_count,
        "plan_name": plan_name,
        "room_name": room.get("name"),
        "breakfast": breakfast,
        "lunch": lunch,
        "dinner": dinner,
        "url": f"https://www.ikyu.com/{accommodation_id}/?accommodation_types=HOTEL,INN,BUSINESS,RESORT_HOTEL&adc=1&lc=1&pln={plan_id}&ppc=2&rc=1&rm={room_id}&si=1&st=1&top=plans",
        "prices": []
    }

    # Fetch calendar
    payload_calendar = {
        "query": """
        query Search($accommodationId: AccommodationIdScalar!, $roomId: RoomIdScalar!, $planId: PlanIdScalar!, $input: RoomPlanCalendarInput!, $currency: Currency!) {
          accommodation(accommodationId: $accommodationId) {
            roomPlan(
              roomId: $roomId
              planId: $planId
            ) {
              calendar(input: $input) {
                date
                discountAmount(currency: $currency)
              }
            }
          }
        }
        """,
        "variables": {
            "accommodationId": accommodation_id,
            "roomId": room_id,
            "planId": plan_id,
            "input": {
                "lodgingCount": 1,
                "peopleCount": adult_count,
                "roomCount": 1,
                "searchType": "1",
                "discount": True,
                "startDate": now_date.strftime("%Y-%m-%d"),
                "endDate": limit_date.strftime("%Y-%m-%d"),
                "preview": False
            },
            "currency": "JPY"
        },
        "operationName": "Search"
    }
    try:
        calendar_data = infinite_retry_post(payload_calendar).json()
        calendar = calendar_data.get('data', {}).get('accommodation', {}).get('roomPlan', {}).get('calendar', []) or []
        for entry in calendar:
            entry_date = datetime.strptime(entry.get("date"), "%Y-%m-%d").date()
            discount_amount = entry.get("discountAmount")
            if now_date <= entry_date < limit_date and discount_amount is not None and discount_amount != 0:
                plan_obj["prices"].append({
                    "date": entry.get("date"),
                    "price": discount_amount
                })
    except Exception as e:
        print(f"          Error extracting prices for room {room_id}: {e}")

    return plan_obj

def process_hotel(accommodation_id):
    thread_id = threading.get_ident()
    with lock:
        running_hotels.add(accommodation_id)
        print(f"[START] Hotel {accommodation_id} by Thread {thread_id} | Currently running hotels: {running_hotels}")
        print(f"Active threads: {threading.active_count()}")

    process_hash_id = get_process_hash_id()
    last_updated_at = get_last_updated_at()
    now_local = get_now()
    now_date = now_local.date()
    limit_date = (now_local + timedelta(days=180)).date()
    collected_rooms = []

    try:
        for adult_count in range(1, 7):
            plan_edges = fetch_plans(accommodation_id, adult_count)
            for plan_edge in plan_edges:
                plan_node = plan_edge.get('node', {})
                plan_id = plan_node.get("planId")
                plan_name = plan_node.get("name")
                meal = plan_node.get("meal", {})
                meal_code = meal.get("code", "000")
                breakfast, lunch, dinner = meal_code_to_flags(meal_code)
                if not plan_id:
                    continue
                room_edges = fetch_rooms(accommodation_id, plan_id, adult_count)
                room_args = [
                    (accommodation_id, plan_id, plan_name, meal_code, breakfast, lunch, dinner,
                     room_edge, now_date, limit_date, adult_count)
                    for room_edge in room_edges
                ]
                num_rooms = len(room_args)
                if num_rooms > 0:
                    with ThreadPoolExecutor(max_workers=num_rooms) as room_executor:
                        room_futures = [room_executor.submit(fetch_room_and_calendar, arg) for arg in room_args]
                        for room_future in as_completed(room_futures):
                            plan_obj = room_future.result()
                            if plan_obj:
                                collected_rooms.append(plan_obj)
    except Exception as e:
        print(f"Hotel {accommodation_id}: Error: {e}")

    hotel_data = {
        "hotel_id": accommodation_id,
        "last_updated_at": last_updated_at,
        "process_hash_id": process_hash_id,
        "plans": collected_rooms
    }
    # Append to shared results list (thread-safe)
    with results_lock:
        all_hotels.append(hotel_data)

    print(f"[END]   Hotel {accommodation_id} by Thread {thread_id}")
    with lock:
        running_hotels.remove(accommodation_id)
        print(f"Currently running hotels after END: {running_hotels}")

def main():
    hotel_ids = read_hotel_ids()

    try:
        with ThreadPoolExecutor(max_workers=1) as hotel_executor:
            hotel_futures = [hotel_executor.submit(process_hotel, hotel_id) for hotel_id in hotel_ids]
            for hotel_future in as_completed(hotel_futures):
                hotel_future.result()
    except KeyboardInterrupt:
        print("\nScript interrupted by user. Safe to resume.")
        sys.exit(0)

    # Write all results to a single JSON file
    with open(final_file, "w", encoding="utf-8") as f:
        json.dump(all_hotels, f, ensure_ascii=False, indent=2)
    print(f"\nAll hotels data collection complete. All hotels saved to {final_file}")

if __name__ == "__main__":
    run_all_hotels()
