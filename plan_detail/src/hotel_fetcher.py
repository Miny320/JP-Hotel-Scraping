import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import time
import signal
import sys
from datetime import datetime, timedelta
from .config import input_ids_file, final_file
from .utils import get_process_hash_id, get_last_updated_at, get_now
from .plan_fetcher import fetch_plans, meal_code_to_flags
from .room_fetcher import fetch_rooms_batch
from .calendar_fetcher import fetch_room_and_calendar, fetch_calendars_batch

BUFFER_FILE = final_file  # Use the final file directly
write_lock = threading.Lock()

# Set your desired parallelism here
batch_size = 20

# Process tracking variables
process_stats = {
    "process_hash_id": get_process_hash_id(),
    "thread_num": "0",
    "PID": os.getpid(),
    "batches_processed": 0,
    "current_state": "RUNNING",
    "finish_reason": "",
    "finish_time": None,
    "hotels_in_chunk": 0,
    "hotels_processed": 0,
    "mongodb_to_preimport_total_time": "",
    "mysql_exported": False,
    "preimport_to_production_total_time": "",
    "scope": "daily",
    "start_time": datetime.now(),
    "total_time": ""
}

def signal_handler(signum, frame):
    """Handle interrupt signals gracefully"""
    print(f"\nReceived signal {signum}. Gracefully shutting down...")
    mark_process_finished("interrupted")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def update_process_log():
    """Update the price_logo.txt file with current process statistics"""
    if process_stats["finish_time"]:
        total_duration = process_stats["finish_time"] - process_stats["start_time"]
        process_stats["total_time"] = str(total_duration).split('.')[0]  # Remove microseconds
    
    log_data = {
        "_id": f"ObjectId(\"{process_stats['process_hash_id']}\")",
        "process_hash_id": process_stats["process_hash_id"],
        "thread_num": process_stats["thread_num"],
        "PID": process_stats["PID"],
        "batches_processed": process_stats["batches_processed"],
        "current_state": process_stats["current_state"],
        "finish_reason": process_stats["finish_reason"],
        "finish_time": process_stats["finish_time"].isoformat() + "+0000" if process_stats["finish_time"] else "",
        "hotels_in_chunk": process_stats["hotels_in_chunk"],
        "hotels_processed": process_stats["hotels_processed"],
        "mongodb_to_preimport_total_time": process_stats["mongodb_to_preimport_total_time"],
        "mysql_exported": process_stats["mysql_exported"],
        "preimport_to_production_total_time": process_stats["preimport_to_production_total_time"],
        "scope": process_stats["scope"],
        "start_time": process_stats["start_time"].isoformat() + "+0000",
        "total_time": process_stats["total_time"]
    }
    
    with open("price_logo.txt", "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

def mark_process_finished(reason="finished"):
    """Mark the process as finished and update the log"""
    process_stats["current_state"] = "FINISHED"
    process_stats["finish_reason"] = reason
    process_stats["finish_time"] = datetime.now()
    update_process_log()

def mark_process_running():
    """Mark the process as running and update the log"""
    process_stats["current_state"] = "RUNNING"
    process_stats["finish_reason"] = ""
    process_stats["finish_time"] = None
    update_process_log()

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
    print(f"[Hotel {accommodation_id}] Starting processing...")
    process_hash_id = get_process_hash_id()
    last_updated_at = get_last_updated_at()
    now_local = get_now()
    now_date = now_local.date()
    limit_date = (now_local + timedelta(days=180)).date()
    plans = []
    
    try:
        for adult_count in range(1, 7):
            print(f"[Hotel {accommodation_id}] Processing adult_count: {adult_count}")
            
            # Fetch plans for this adult count
            plan_edges = fetch_plans(accommodation_id, adult_count)
            if not plan_edges:
                print(f"[Hotel {accommodation_id}] No plans found for adult_count: {adult_count}")
                continue
            
            print(f"[Hotel {accommodation_id}] Found {len(plan_edges)} plans for adult_count: {adult_count}")
            
            plan_id_to_edge = {}
            plan_ids = []
            for plan_edge in plan_edges:
                plan_node = plan_edge.get('node', {})
                plan_id = plan_node.get("planId")
                if plan_id:
                    plan_ids.append(plan_id)
                    plan_id_to_edge[plan_id] = plan_edge
            
            if not plan_ids:
                print(f"[Hotel {accommodation_id}] No valid plan IDs found for adult_count: {adult_count}")
                continue
            
            # Batch fetch all rooms for these plans
            print(f"[Hotel {accommodation_id}] Fetching rooms for {len(plan_ids)} plans...")
            plan_rooms_dict = fetch_rooms_batch(accommodation_id, plan_ids, adult_count)
            
            # Prepare all (plan, room) pairs for batch calendar fetch
            room_plan_args = []
            plan_room_meta = {}  # (plan_id, room_id) -> (plan_name, meal_code, breakfast, lunch, dinner)
            
            total_rooms = 0
            for plan_id in plan_ids:
                plan_edge = plan_id_to_edge[plan_id]
                plan_node = plan_edge.get('node', {})
                plan_name = plan_node.get("name")
                meal = plan_node.get("meal", {})
                meal_code = meal.get("code", "000")
                breakfast, lunch, dinner = meal_code_to_flags(meal_code)
                room_edges = plan_rooms_dict.get(plan_id, [])
                total_rooms += len(room_edges)
                
                for room_edge in room_edges:
                    node = room_edge.get('node', {})
                    room = node.get('room', {})
                    room_id = room.get("roomId")
                    room_name = room.get("name")
                    if not room_id:
                        continue
                    room_plan_args.append((plan_id, room_id, room_name, plan_name, meal_code, breakfast, lunch, dinner, adult_count))
                    plan_room_meta[(plan_id, room_id)] = (plan_name, meal_code, breakfast, lunch, dinner)
            
            print(f"[Hotel {accommodation_id}] Found {total_rooms} rooms across {len(plan_ids)} plans")
            
            if not room_plan_args:
                print(f"[Hotel {accommodation_id}] No valid room-plan pairs found for adult_count: {adult_count}")
                continue
            
            # Batch fetch all calendars/prices for these (plan, room) pairs
            print(f"[Hotel {accommodation_id}] Fetching calendars for {len(room_plan_args)} room-plan pairs...")
            calendar_results = fetch_calendars_batch(accommodation_id, room_plan_args, now_date, limit_date)
            
            # Organize results by plan
            plan_rooms_map = {plan_id: [] for plan_id in plan_ids}
            for (plan_id, room_id), plan_obj in calendar_results.items():
                plan_rooms_map[plan_id].append({
                    "room_code": plan_obj["room_code"],
                    "room_name": plan_obj["room_name"],
                    "prices": plan_obj["prices"]
                })
            
            # Create plan objects
            for plan_id in plan_ids:
                plan_edge = plan_id_to_edge[plan_id]
                plan_node = plan_edge.get('node', {})
                plan_name = plan_node.get("name")
                meal = plan_node.get("meal", {})
                meal_code = meal.get("code", "000")
                breakfast, lunch, dinner = meal_code_to_flags(meal_code)
                rooms = plan_rooms_map.get(plan_id, [])
                plans.append({
                    "plan_id": plan_id,
                    "plan_name": plan_name,
                    "checked_adult_count": adult_count,
                    "breakfast": breakfast,
                    "lunch": lunch,
                    "dinner": dinner,
                    "rooms": rooms
                })
            
            print(f"[Hotel {accommodation_id}] Completed adult_count: {adult_count} - {len(plans)} total plans so far")
    
    except Exception as e:
        print(f"[Hotel {accommodation_id}] Error during processing: {e}")
        import traceback
        traceback.print_exc()
    
    hotel_data = {
        "hotel_id": accommodation_id,
        "last_updated_at": last_updated_at,
        "process_hash_id": process_hash_id,
        "plans": plans
    }
    
    print(f"[Hotel {accommodation_id}] Completed processing - {len(plans)} total plans")
    return hotel_data

# Print a simple progress bar
def print_progress(processed, total, bar_length=40):
    percent = processed / total
    filled = int(bar_length * percent)
    bar = '█' * filled + '-' * (bar_length - filled)
    print(f"[Progress] |{bar}| {processed}/{total} ({percent:.1%})", end='\r')

# Use a single ThreadPoolExecutor for all hotels, always keeping up to batch_size in parallel
def run_all_hotels():
    # Initialize process log
    mark_process_running()
    print(f"Process started with PID: {process_stats['PID']}")
    print(f"Process hash ID: {process_stats['process_hash_id']}")
    
    hotel_ids = read_hotel_ids()
    completed_ids = read_completed_hotel_ids()
    hotel_ids_to_process = [hid for hid in hotel_ids if hid not in completed_ids]
    total = len(hotel_ids)
    
    print(f"Total hotels: {total}")
    print(f"Already completed: {len(completed_ids)}")
    print(f"Hotels to process: {len(hotel_ids_to_process)}")
    
    # Don't clear the buffer file; append if resuming
    if not os.path.exists(BUFFER_FILE):
        with open(BUFFER_FILE, "w", encoding="utf-8") as f:
            pass
    
    print(f"Starting hotel scraping with up to {batch_size} hotels in parallel...")
    print(f"Data will be saved to: {BUFFER_FILE}")
    
    processed_count = 0
    batch_count = 0
    
    # Process hotels in batches to ensure continuous processing
    while hotel_ids_to_process:
        # Take a batch of hotels to process
        current_batch = hotel_ids_to_process[:batch_size]
        hotel_ids_to_process = hotel_ids_to_process[batch_size:]
        
        batch_count += 1
        process_stats["batches_processed"] = batch_count
        process_stats["hotels_in_chunk"] = len(current_batch)
        process_stats["hotels_processed"] = processed_count
        update_process_log()
        
        print(f"\n=== Processing Batch {batch_count} ({len(current_batch)} hotels) ===")
        print(f"Remaining hotels: {len(hotel_ids_to_process)}")
        
        with ThreadPoolExecutor(max_workers=batch_size) as hotel_executor:
            hotel_futures = {}
            for hotel_id in current_batch:
                future = hotel_executor.submit(process_hotel, hotel_id)
                hotel_futures[future] = hotel_id
            
            for hotel_future in as_completed(hotel_futures):
                hotel_id = hotel_futures[hotel_future]
                try:
                    print(f"[Main] Waiting for result of hotel {hotel_id}...")
                    hotel_data = hotel_future.result()
                    print(f"[Main] Got result for hotel {hotel_id}.")
                    
                    if hotel_data:
                        # Immediately save hotel_data to buffer file (thread-safe)
                        with write_lock:
                            with open(BUFFER_FILE, "a", encoding="utf-8") as f:
                                f.write(json.dumps(hotel_data, ensure_ascii=False, separators=(',', ':')) + "\n")
                                f.flush()  # Ensure data is written immediately
                        print(f"[Hotel {hotel_data['hotel_id']}] Data saved to buffer file.")
                        processed_count += 1
                        process_stats["hotels_processed"] = processed_count
                        update_process_log()
                    else:
                        print(f"[Hotel {hotel_id}] No data returned from process_hotel.")
                        
                except Exception as e:
                    print(f"[Main] Exception occurred while processing hotel {hotel_id}: {e}")
                    import traceback
                    traceback.print_exc()
                
                # Update progress
                print_progress(processed_count, total)
        
        print(f"=== Completed Batch {batch_count} ===")
        print(f"Total processed so far: {processed_count}/{total}")
        
        # Update process log after each batch
        update_process_log()
    
    # Mark process as finished
    mark_process_finished("finished")
    
    print(f"\n\nAll hotels data collection complete. Total processed: {processed_count} hotels.")
    print(f"All data saved to: {BUFFER_FILE}")
    print("Process log saved to: price_logo.txt")
    return True 