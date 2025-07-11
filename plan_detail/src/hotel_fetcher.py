import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from .config import input_ids_file, final_file
from .utils import get_process_hash_id, get_last_updated_at, get_now
from .plan_fetcher import fetch_plans, meal_code_to_flags
from .room_fetcher import fetch_rooms
from .calendar_fetcher import fetch_room_and_calendar
from datetime import timedelta

BUFFER_FILE = 'ikyu_all_hotels_buffer.jsonl'
write_lock = threading.Lock()

# Set your desired parallelism here
batch_size = 100

# Read hotel IDs from file
def read_hotel_ids():
    hotel_ids = []
    with open(input_ids_file, "r", encoding="utf-8") as f:
        hotels = json.load(f)
        for obj in hotels:
            hotel_ids.append(obj["hotel_id"])
    return hotel_ids

# Read already processed hotel IDs from buffer file
def read_completed_hotel_ids():
    completed = set()
    if os.path.exists(BUFFER_FILE):
        with open(BUFFER_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    completed.add(obj["hotel_id"])
                except Exception:
                    continue
    return completed

# Get the current number of processed hotels (lines in buffer file)
def get_processed_count():
    if not os.path.exists(BUFFER_FILE):
        return 0
    with open(BUFFER_FILE, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)

# Process a single hotel and return its structured data
def process_hotel(accommodation_id):
    process_hash_id = get_process_hash_id()
    last_updated_at = get_last_updated_at()
    now_local = get_now()
    now_date = now_local.date()
    limit_date = (now_local + timedelta(days=180)).date()
    plans = []
    # --- Collect all plan_edges for all adult counts first ---
    all_plan_edges = []
    for adult_count in range(1, 7):
        plan_edges = fetch_plans(accommodation_id, adult_count)
        for plan_edge in plan_edges:
            all_plan_edges.append((plan_edge, adult_count))
    total_plans = len(all_plan_edges)
    plan_idx = 0
    # --- Process each plan and show plan progress ---
    try:
        for plan_edge, adult_count in all_plan_edges:
            plan_idx += 1
            print(f"[Hotel {accommodation_id}] Plan progress: {plan_idx}/{total_plans}", end='\r')
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
            # Fetch all rooms for this plan in parallel
            rooms = []
            if room_args:
                with ThreadPoolExecutor(max_workers=min(len(room_args), 10)) as room_executor:
                    room_futures = [room_executor.submit(fetch_room_and_calendar, arg) for arg in room_args]
                    for room_future in as_completed(room_futures):
                        plan_obj = room_future.result()
                        if plan_obj:
                            rooms.append({
                                "room_code": plan_obj["room_code"],
                                "room_name": plan_obj["room_name"],
                                "prices": plan_obj["prices"]
                            })
            plans.append({
                "plan_id": plan_id,
                "plan_name": plan_name,
                "checked_adult_count": adult_count,
                "breakfast": breakfast,
                "lunch": lunch,
                "dinner": dinner,
                "rooms": rooms
            })
        if total_plans > 0:
            print(f"[Hotel {accommodation_id}] Plan progress: {total_plans}/{total_plans}")
    except Exception as e:
        print(f"Hotel {accommodation_id}: Error: {e}")
    hotel_data = {
        "hotel_id": accommodation_id,
        "last_updated_at": last_updated_at,
        "process_hash_id": process_hash_id,
        "plans": plans
    }
    return hotel_data

# Print a simple progress bar
def print_progress(processed, total, bar_length=40):
    percent = processed / total
    filled = int(bar_length * percent)
    bar = '█' * filled + '-' * (bar_length - filled)
    print(f"[Progress] |{bar}| {processed}/{total} ({percent:.1%})", end='\r')

# Use a single ThreadPoolExecutor for all hotels, always keeping up to batch_size in parallel
def run_all_hotels():
    hotel_ids = read_hotel_ids()
    completed_ids = read_completed_hotel_ids()
    hotel_ids_to_process = [hid for hid in hotel_ids if hid not in completed_ids]
    total = len(hotel_ids)
    # Don't clear the buffer file; append if resuming
    if not os.path.exists(BUFFER_FILE):
        with open(BUFFER_FILE, "w", encoding="utf-8") as f:
            pass
    print(f"Starting hotel scraping with up to {batch_size} in parallel...")
    with ThreadPoolExecutor(max_workers=batch_size) as hotel_executor:
        hotel_futures = {hotel_executor.submit(process_hotel, hotel_id): hotel_id for hotel_id in hotel_ids_to_process}
        for hotel_future in as_completed(hotel_futures):
            hotel_data = hotel_future.result()
            if hotel_data:
                with write_lock:
                    with open(BUFFER_FILE, "a", encoding="utf-8") as f:
                        f.write(json.dumps(hotel_data, ensure_ascii=False) + "\n")
            processed = get_processed_count()
            print_progress(processed, total)
    print(f"\n\nAll hotels data collection complete. Total: {get_processed_count()} hotels. Converting buffer to pretty JSON array...")
    # Read buffer and write pretty JSON array
    hotels = []
    with open(BUFFER_FILE, "r", encoding="utf-8") as f:
        for line in f:
            hotels.append(json.loads(line))
    with open(final_file, "w", encoding="utf-8") as f:
        json.dump(hotels, f, ensure_ascii=False, indent=2)
    print(f"All hotels saved to {final_file} (pretty JSON array)")
    # Optionally, remove the buffer file
    try:
        os.remove(BUFFER_FILE)
    except Exception:
        pass
    return True 