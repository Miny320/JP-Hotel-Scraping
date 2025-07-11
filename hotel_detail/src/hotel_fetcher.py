import json
import time
import logging
import requests
from typing import List, Dict, Any
from .config import PROXIES, HEADERS, URL, JSON_FILENAME
from .utils import get_last_updated_at, get_process_hash_id, to_e164_jp_phone

logging.basicConfig(level=logging.INFO)

class HotelFetcher:
    def __init__(self):
        self.json_filename = JSON_FILENAME

    def infinite_retry_post(self, payload) -> any:
        wait_time = 5
        while True:
            try:
                response = requests.post(URL, headers=HEADERS, proxies=PROXIES, json=payload, timeout=60)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError as e:
                logging.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
                logging.error(f"Payload was: {json.dumps(payload, ensure_ascii=False)}")
                time.sleep(wait_time)
                wait_time = min(wait_time * 2, 60)
            except Exception as e:
                logging.error(f"Request failed: {e}. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                wait_time = min(wait_time * 2, 60)

    def fetch_all_hotels(self) -> List[Dict[str, any]]:
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
            "first": 20,
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
        data = self.infinite_retry_post(payload)
        accommodations = data.get('data', {}).get('listPageIkyu', {}).get('accommodations', {})
        total_count = accommodations.get('totalCount', 0)
        logging.info(f"Total accommodations found: {total_count}")
        # Request all data at once
        base_variables["first"] = total_count
        base_variables["offset"] = 0
        payload = {
            "query": query,
            "variables": base_variables,
            "operationName": "ListPageDataIkyu"
        }
        data = self.infinite_retry_post(payload)
        accommodations = data.get('data', {}).get('listPageIkyu', {}).get('accommodations', {})
        edges = accommodations.get('edges', [])
        all_hotels = []
        all_hotel_ids = set()
        for idx, edge in enumerate(edges):
            node = edge.get('node', {})
            acc_id = node.get('accommodationId')
            name = node.get('name')
            if acc_id and acc_id not in all_hotel_ids:
                all_hotel_ids.add(acc_id)
                rating2 = node.get("rating2") or {}
                phone_raw = node.get("phoneNumber")
                hotel_data = {
                    "id": idx,
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
                    "hotel_location": None
                }
                all_hotels.append(hotel_data)
        logging.info(f"Fetching location info for {len(all_hotels)} hotels in batches of 1000...")
        self.fetch_locations(all_hotels, 1000)
        return all_hotels

    def fetch_locations(self, all_hotels: List[Dict[str, any]], batch_size: int):
        location_query = """
query AccommodationMap($accommodationId: AccommodationIdScalar!) {
  accommodation(accommodationId: $accommodationId) {
    latitude
    longitude
  }
}
"""
        hotel_id_to_idx = {hotel["hotel_id"]: idx for idx, hotel in enumerate(all_hotels)}
        hotel_ids = [hotel["hotel_id"] for hotel in all_hotels]
        for start in range(0, len(hotel_ids), batch_size):
            batch = hotel_ids[start:start+batch_size]
            payload = [
                {
                    "operationName": "AccommodationMap",
                    "query": location_query,
                    "variables": {"accommodationId": hid}
                }
                for hid in batch
            ]
            try:
                results = self.infinite_retry_post(payload)
                for hid, result in zip(batch, results):
                    acc = result.get("data", {}).get("accommodation", {})
                    latitude = acc.get("latitude")
                    longitude = acc.get("longitude")
                    idx = hotel_id_to_idx[hid]
                    if latitude is not None and longitude is not None:
                        all_hotels[idx]["hotel_location"] = [longitude, latitude]
                    else:
                        all_hotels[idx]["hotel_location"] = None
            except Exception as e:
                logging.error(f"Failed to get location for batch starting at {start}: {e}")
                for hid in batch:
                    idx = hotel_id_to_idx[hid]
                    all_hotels[idx]["hotel_location"] = None
            # Save progress after each batch
            logging.info(f"Processed {min(start+batch_size, len(hotel_ids))}/{len(hotel_ids)} hotels")
            with open(self.json_filename, "w", encoding="utf-8") as f:
                json.dump(all_hotels, f, ensure_ascii=False, indent=2)
        logging.info(f"Total hotels with location saved: {len(all_hotels)}") 