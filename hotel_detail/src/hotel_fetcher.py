import json
import time
import logging
import requests
from typing import List, Dict, Any
from common.config import PROXIES, HEADERS, URL
from common.utils import get_last_updated_at, get_process_hash_id, to_e164_jp_phone, infinite_retry_post
import pymongo
import os
from pymongo import UpdateOne
import copy
import concurrent.futures

logging.basicConfig(level=logging.INFO)

def stream_hotels_to_mongo(mongodb_uri=None):
    """
    Connect to MongoDB and return client and hotels collection for hotel data.
    """
    mongodb_uri = (
        "mongodb://myfamily0402:UohZ4dEi5Ff0uD8J@"
        "ac-irxctku-shard-00-00.rgnmyxs.mongodb.net:27017,"
        "ac-irxctku-shard-00-01.rgnmyxs.mongodb.net:27017,"
        "ac-irxctku-shard-00-02.rgnmyxs.mongodb.net:27017/"
        "?ssl=true&replicaSet=atlas-116ae1-shard-0&authSource=admin"
    )
    client = pymongo.MongoClient(mongodb_uri)
    db_name = "hotel_database"
    db = client[db_name]
    hotels_collection = db['hotels_info']
    return client, hotels_collection

class HotelFetcher:
    """
    Fetches hotel details, locations, and manages hotel data updates.
    """
    def __init__(self, hotels_collection=None):
        """
        Initialize HotelFetcher with a MongoDB hotels collection.
        """
        self.hotels_collection = hotels_collection

    def fetch_hotel_detail(self, hotel_id):
        """
        Fetch detailed information for a single hotel by ID.
        """
        detail_query = '''
        query AccommodationDetail($accommodationId: ID!) {
          accommodationDetail(accommodationId: $accommodationId) {
            accommodationId
            name
            location {
              lat
              lng
            }
            address
          }
        }
        '''
        variables = {"accommodationId": hotel_id}
        payload = {
            "query": detail_query,
            "variables": variables,
            "operationName": "AccommodationDetail"
        }
        data = infinite_retry_post(payload)
        return data.get('data', {}).get('accommodationDetail', {})

    def fetch_hotel_location(self, hotel_id):
        """
        Fetch latitude, longitude, and address for a hotel by ID.
        """
        location_query = '''
        query AccommodationMap($accommodationId: AccommodationIdScalar!) {
          accommodation(accommodationId: $accommodationId) {
            latitude
            longitude
            address
            prefecture { name }
            postalCode
            phoneNumber
          }
        }
        '''
        variables = {"accommodationId": hotel_id}
        payload = {
            "query": location_query,
            "variables": variables,
            "operationName": "AccommodationMap"
        }
        data = infinite_retry_post(payload)
        acc = data.get('data', {}).get('accommodation', {})
        if acc and acc.get('latitude') is not None and acc.get('longitude') is not None:
            return {
                "lat": acc.get('latitude'),
                "lng": acc.get('longitude')
            }, acc.get('address')
        return None, acc.get('address')

    def compare_hotel_data(self, existing_data, new_data):
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

    def fetch_hotels_locations_batch(self, hotel_ids):
        """
        Fetch locations for a batch of hotel IDs.
        """
        location_query = '''
        query AccommodationLocations($ids: [AccommodationIdScalar!]!, $first: Int!) {
          accommodations(accommodationIds: $ids, first: $first) {
            edges {
              node {
                accommodationId
                latitude
                longitude
              }
            }
          }
        }
        '''
        variables = {"ids": hotel_ids, "first": len(hotel_ids)}
        payload = {
            "query": location_query,
            "variables": variables,
            "operationName": "AccommodationLocations"
        }
        data = infinite_retry_post(payload)
        accs = data.get('data', {}).get('accommodations', {}).get('edges', [])
        loc_map = {}
        addr_map = {}
        for edge in accs:
            node = edge.get('node', {})
            acc_id = node.get('accommodationId')
            if acc_id:
                loc = None
                if node.get('latitude') is not None and node.get('longitude') is not None:
                    loc = [node.get('longitude'), node.get('latitude')]
                loc_map[acc_id] = loc
                addr_map[acc_id] = node.get('address')
        return loc_map, addr_map

    def fetch_all_hotels(self) -> int:
        """
        Fetch all hotels' metadata and update the MongoDB collection.
        Returns the number of hotels processed.
        """
        query = """
query ListPageDataIkyu($first: Int!, $offset: Int!, $searchAccommodationsInput: SearchAccommodationsInput!, $searchRoomsInput: SearchRoomsInput!) {
  listPageIkyu: listPage(
    input: $searchAccommodationsInput
    first: $first
    offset: $offset
  ) {
    accommodations {
      totalCount
      edges {
        node {
          accommodationId
          name
          rating2 {
            average
            roomAmenity
            customerService
            bathroomSpring
            accommodationEquipment
            meal
            satisfaction
            count
          }
          searchRooms2(input: $searchRoomsInput, first: 3) {
            rooms {
              totalCount
            }
          }
          type
          phoneNumber
          postalCode
        }
      }
      pageInfo {
        hasNextPage
      }
    }
  }
}
"""
        base_variables = {
            "first": 1000,
            "offset": 0,
            "searchAccommodationsInput": {
                "discount": True,
                "lodgingCount": 1,
                "peopleCount": 2,
                "roomCount": 1,
                "sortItem": "6",
                "sortOrder": "1",
                "accommodationTypes": ["BUSINESS", "HOTEL", "INN", "RESORT_HOTEL"],
                "majorAreaIds": ["000000"],
                "currency": "JPY"
            },
            "searchRoomsInput": {
                "discount": True,
                "lodgingCount": 1,
                "peopleCount": 2,
                "roomCount": 1,
                "sortItem": "1",
                "sortOrder": "1",
                "preferHighAmount": False,
                "currency": "JPY",
                "onlyOriginalPlans": False
            }
        }
        # First request to get totalCount
        payload = {
            "query": query,
            "variables": base_variables,
            "operationName": "ListPageDataIkyu"
        }
        data = infinite_retry_post(payload)
        accommodations = data.get('data', {}).get('listPageIkyu', {}).get('accommodations', {})
        total_count = accommodations.get('totalCount', 0)
        logging.info(f"Total accommodations found: {total_count}")
        
        all_hotel_ids = set()
        hotels_skipped = 0
        hotels_new = 0
        hotels_updated = 0
        processed_hotel_ids = []
        from datetime import datetime, timezone
        import hashlib
        start_time = datetime.now(timezone.utc)
        current_state = "RUNNING"
        finish_reason = ""
        batch_size = 1000
        offset = 0
        while offset < total_count:
            base_variables["first"] = batch_size
            base_variables["offset"] = offset
            payload = {
                "query": query,
                "variables": base_variables,
                "operationName": "ListPageDataIkyu"
            }
            data = infinite_retry_post(payload)
            accommodations = data.get('data', {}).get('listPageIkyu', {}).get('accommodations', {})
            edges = accommodations.get('edges', [])
            batch_hotels = []
            batch_hotel_ids = []
            for idx, edge in enumerate(edges):
                node = edge.get('node', {})
                acc_id = node.get('accommodationId')
                name = node.get('name')
                if not acc_id or acc_id in all_hotel_ids:
                    hotels_skipped += 1
                    continue
                all_hotel_ids.add(acc_id)
                rating2 = node.get("rating2") or {}
                phone_raw = node.get("phoneNumber")
                hotel_data = {
                    "hotel_id": acc_id,
                    "hotel_name": name,
                    "hotel_overall_score": rating2.get("average"),
                    "hotel_state": "ALIVE",
                    "rating": {
                        "reviews_count": rating2.get("count"),
                        "room_score": rating2.get("roomAmenity"),
                        "bath_score": rating2.get("bathroomSpring"),
                        "meal_score": rating2.get("meal"),
                        "service_score": rating2.get("customerService"),
                        "accomodation_score": rating2.get("accommodationEquipment"),
                        "satisfaction_score": rating2.get("satisfaction"),
                    },
                    "hotel_url": f"https://www.ikyu.com/{acc_id}",
                    "hotel_type": node.get("type"),
                    "hotel_rooms_count": (
                        node.get("searchRooms2", {}).get("rooms", {}).get("totalCount")
                        if node.get("searchRooms2") and node.get("searchRooms2").get("rooms")
                        else None
                    ),
                    "phone": to_e164_jp_phone(phone_raw),
                    "zip": node.get("postalCode"),
                    "last_updated_at": get_last_updated_at(),
                    "process_hash_id": get_process_hash_id(),
                    # location fields will be added after batch fetch
                }
                batch_hotels.append(hotel_data)
                batch_hotel_ids.append(acc_id)
            logging.info(f"Collected {len(batch_hotels)} hotel records in batch at offset {offset}.")
            # Fetch all locations in a single batch query for this batch
            location_results, address_results = self.fetch_hotels_locations_batch(batch_hotel_ids)
            # Merge location info into hotel records
            for hotel in batch_hotels:
                hid = hotel["hotel_id"]
                hotel["hotel_location"] = location_results.get(hid)
                # hotel_address field removed
            # Upload in batches and track new/updated
            if self.hotels_collection is not None and batch_hotels:
                batch_ops = []
                batch_hotel_ids = []
                batch_new_count = 0
                batch_updated_count = 0
                # Get all hotel IDs in this batch
                batch_hotel_ids_list = [h["hotel_id"] for h in batch_hotels]
                # Fetch all existing hotels in this batch at once
                existing_hotels = {}
                if batch_hotel_ids_list:
                    existing_cursor = self.hotels_collection.find({"hotel_id": {"$in": batch_hotel_ids_list}})
                    for existing_hotel in existing_cursor:
                        existing_hotels[existing_hotel["hotel_id"]] = existing_hotel
                # Process each hotel in the batch
                for hotel_data in batch_hotels:
                    hotel_id = hotel_data["hotel_id"]
                    if hotel_id not in existing_hotels:
                        # New hotel - insert
                        batch_ops.append(UpdateOne(
                            {"hotel_id": hotel_id},
                            {"$set": hotel_data},
                            upsert=True
                        ))
                        batch_new_count += 1
                        batch_hotel_ids.append(hotel_id)
                    else:
                        # Existing hotel - compare data
                        if self.compare_hotel_data(existing_hotels[hotel_id], hotel_data):
                            # Data is different - update
                            batch_ops.append(UpdateOne(
                                {"hotel_id": hotel_id},
                                {"$set": hotel_data}
                            ))
                            batch_updated_count += 1
                            batch_hotel_ids.append(hotel_id)
                # Execute batch operations if any
                if batch_ops:
                    result = self.hotels_collection.bulk_write(batch_ops, ordered=False)
                    processed_hotel_ids.extend(batch_hotel_ids)
                    hotels_new += batch_new_count
                    hotels_updated += batch_updated_count
                    skipped_count = len(batch_hotels) - batch_new_count - batch_updated_count
                    logging.info(f"Batch at offset {offset}: {len(batch_hotels)} hotels processed - {batch_new_count} new, {batch_updated_count} updated, {skipped_count} unchanged")
                else:
                    logging.info(f"Batch at offset {offset}: {len(batch_hotels)} hotels - all unchanged")
            offset += batch_size
        finish_time = datetime.now(timezone.utc)
        total_time = finish_time - start_time
        total_mongo_hotels = self.hotels_collection.count_documents({}) if self.hotels_collection is not None else len(all_hotel_ids)
        hotels_processed = hotels_new + hotels_updated
        hotels_unprocessed = total_count - hotels_processed
        log_data = {
            "_id": hashlib.md5((str(start_time.timestamp()) + str(os.getpid())).encode()).hexdigest(),
            "process_hash_id": get_process_hash_id(),
            "current_state": "FINISHED",
            "detailed_stats": {
                "hotels_skipped": hotels_skipped,
                "hotels_alive": hotels_processed,  # Approximation
                "hotels_dead": 0,
                "hotels_has_logos": 0,
                "hotels_no_logos": 0
            },
            "finish_reason": "finished",
            "finish_time": finish_time.isoformat(timespec='milliseconds'),
            "hotels_new": hotels_new,
            "hotels_processed": hotels_processed,
            "hotels_unprocessed": hotels_unprocessed,
            "hotels_updated": hotels_updated,
            "start_time": start_time.isoformat(timespec='milliseconds'),
            "total_mongo_hotels": total_mongo_hotels,
            "total_sitemap_hotels": total_count,
            "total_time": str(total_time),
            "processed_hotel_ids": processed_hotel_ids
        }
        return hotels_processed, log_data 