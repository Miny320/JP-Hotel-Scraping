import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import time
import signal
import sys
from datetime import datetime, timedelta, timezone
from common.config import HOTEL_JSON, PLAN_FINAL_FILE
from common.utils import get_process_hash_id, get_last_updated_at, get_now, infinite_retry_post
from .plan_fetcher import fetch_plans, meal_code_to_flags
from .room_fetcher import fetch_rooms_batch
from .calendar_fetcher import fetch_room_and_calendar, fetch_calendars_batch
import pymongo
import copy

write_lock = threading.Lock()

def compare_hotel_data(existing_data, new_data):
    """
    Compare existing hotel data with new data to determine if an update is needed.
    Returns True if data is different and needs update, False if identical.
    """
    # Fields to exclude from comparison (timestamps, process IDs, etc.)
    exclude_fields = {'last_updated_at', 'process_hash_id', '_id'}
    
    # Create copies to avoid modifying original data
    existing_copy = copy.deepcopy(existing_data)
    new_copy = copy.deepcopy(new_data)
    
    # Remove excluded fields from both copies
    for field in exclude_fields:
        existing_copy.pop(field, None)
        new_copy.pop(field, None)
    
    # Compare the cleaned data
    return existing_copy != new_copy

batch_size = 20

def signal_handler(signum, frame):
    print(f"\nReceived signal {signum}. Gracefully shutting down...")
    mark_process_finished("interrupted")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def update_process_log():
    if process_stats["finish_time"]:
        total_duration = process_stats["finish_time"] - process_stats["start_time"]
        process_stats["total_time"] = str(total_duration).split('.')[0]
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
    return log_data

def mark_process_finished(reason="finished"):
    process_stats["current_state"] = "FINISHED"
    process_stats["finish_reason"] = reason
    process_stats["finish_time"] = datetime.now()
    return update_process_log()

def mark_process_running():
    process_stats["current_state"] = "RUNNING"
    process_stats["finish_reason"] = ""
    process_stats["finish_time"] = None
    return update_process_log()

def read_hotel_ids_from_mongo(hotels_collection):
    hotel_ids = []
    for doc in hotels_collection.find({}, {"hotel_id": 1}):
        hotel_ids.append(doc["hotel_id"])
    return hotel_ids

def run_all_hotels():
    """
    Main function to fetch plan and room details for all hotels and update MongoDB.
    """
    # MongoDB setup
    mongodb_uri = (
        "mongodb://myfamily0402:UohZ4dEi5Ff0uD8J@"
        "ac-irxctku-shard-00-00.rgnmyxs.mongodb.net:27017,"
        "ac-irxctku-shard-00-01.rgnmyxs.mongodb.net:27017,"
        "ac-irxctku-shard-00-02.rgnmyxs.mongodb.net:27017/"
        "?ssl=true&replicaSet=atlas-116ae1-shard-0&authSource=admin"
    )
    client = pymongo.MongoClient(mongodb_uri)
    db = client["hotel_database"]
    hotels_collection = db["hotels_info"]
    plan_price_collection = db["plan_prices"]
    plan_log_collection = db["plan_log"]

    process_stats = {
        "_id": None,  # will be set at start
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
        "start_time": datetime.now(timezone.utc),
        "total_time": ""
    }

    def update_log():
        log_data = process_stats.copy()
        import hashlib, bson
        if not log_data["_id"]:
            # Fix: concatenate as string, then encode
            hash_input = str(log_data["process_hash_id"]) + str(log_data["PID"])
            log_data["_id"] = bson.ObjectId(hashlib.md5(hash_input.encode()).hexdigest()[:24])
        for k in ["start_time", "finish_time"]:
            if log_data[k] and not isinstance(log_data[k], str):
                log_data[k] = log_data[k].isoformat()
        plan_log_collection.delete_one({"_id": log_data["_id"]})
        plan_log_collection.insert_one(log_data)

    # Use MongoDB as the source of hotel IDs
    hotel_ids = read_hotel_ids_from_mongo(hotels_collection)
    total = len(hotel_ids)
    processed_count = 0
    batch_count = 0
    start_time = process_stats["start_time"]
    update_log()

    for batch_start in range(0, total, batch_size):
        current_batch = hotel_ids[batch_start:batch_start+batch_size]
        batch_count += 1
        process_stats["batches_processed"] = batch_count
        process_stats["hotels_in_chunk"] = len(current_batch)
        process_stats["hotels_processed"] = processed_count
        update_log()

        with ThreadPoolExecutor(max_workers=batch_size) as hotel_executor:
            hotel_futures = {}
            for hotel_id in current_batch:
                future = hotel_executor.submit(process_hotel, hotel_id)
                hotel_futures[future] = hotel_id

            for hotel_future in as_completed(hotel_futures):
                hotel_id = hotel_futures[hotel_future]
                try:
                    hotel_data = hotel_future.result()
                    if hotel_data:
                        # Upload plan/price data to plan_prices collection
                        plan_price_collection.update_one(
                            {"hotel_id": hotel_data["hotel_id"]},
                            {"$set": hotel_data},
                            upsert=True
                        )
                        processed_count += 1
                        process_stats["hotels_processed"] = processed_count
                        update_log()
                except Exception as e:
                    import traceback
                    traceback.print_exc()

        update_log()

    process_stats["current_state"] = "FINISHED"
    process_stats["finish_reason"] = "finished"
    process_stats["finish_time"] = datetime.now(timezone.utc)
    process_stats["total_time"] = str(process_stats["finish_time"] - start_time)
    update_log()
    client.close()
    print("MongoDB connection closed.")
    print(f"\nAll hotels data collection complete. Total processed: {processed_count} hotels.")

def process_hotel(accommodation_id):
    """
    Process a single hotel: fetch plans, rooms, and calendar data, then update MongoDB.
    """
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
            print(f"[Hotel {accommodation_id}] Fetching rooms for {len(plan_ids)} plans...")
            plan_rooms_dict = fetch_rooms_batch(accommodation_id, plan_ids, adult_count)
            # Prepare all (plan, room) pairs for batch calendar fetch
            room_plan_args = []
            plan_room_meta = {} 
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
            # Fetch calendar/prices for all (plan, room) pairs
            print(f"[Hotel {accommodation_id}] Fetching calendars for {len(room_plan_args)} room-plan pairs...")
            calendar_results = fetch_calendars_batch(accommodation_id, room_plan_args, now_date, limit_date)
            if not calendar_results:
                print(f"[Hotel {accommodation_id}] No price/calendar data found for any room-plan pair (adult_count: {adult_count})")
                continue
            # Organize results by plan, only keep rooms with prices
            plan_rooms_map = {plan_id: [] for plan_id in plan_ids}
            for (plan_id, room_id), plan_obj in calendar_results.items():
                if plan_obj["prices"]:
                    plan_rooms_map[plan_id].append({
                        "room_code": plan_obj["room_code"],
                        "room_name": plan_obj["room_name"],
                        "prices": plan_obj["prices"]
                    })
            # Create plan objects, only keep plans with rooms
            for plan_id in plan_ids:
                plan_edge = plan_id_to_edge[plan_id]
                plan_node = plan_edge.get('node', {})
                plan_name = plan_node.get("name")
                meal = plan_node.get("meal", {})
                meal_code = meal.get("code", "000")
                breakfast, lunch, dinner = meal_code_to_flags(meal_code)
                rooms = plan_rooms_map.get(plan_id, [])
                if rooms:
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
    print(f"Hotel {accommodation_id} - plans found: {len(plans)}")
    if not plans:
        print(f"[WARNING] No plans found for hotel {accommodation_id}")
    # Flatten plans/rooms into a single list as required
    plans_flat = []
    for plan in plans:
        for room in plan["rooms"]:
            plans_flat.append({
                "plan_id": plan["plan_id"],
                "room_code": room["room_code"],
                "checked_adult_count": plan["checked_adult_count"],
                "plan_name": plan["plan_name"],
                "room_name": room["room_name"],
                "breakfast": plan["breakfast"],
                "lunch": plan["lunch"],
                "dinner": plan["dinner"],
                "prices": room["prices"]
            })
    hotel_data = {
        "hotel_id": accommodation_id,
        "last_updated_at": last_updated_at,
        "process_hash_id": process_hash_id,
        "plans": plans_flat
    }
    print(f"[Hotel {accommodation_id}] Completed processing - {len(plans)} total plans")
    return hotel_data 