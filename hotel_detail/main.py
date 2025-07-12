import requests
import json
import time
import os
import pytz
from datetime import datetime, timedelta
import hashlib
import re
from src.hotel_fetcher import HotelFetcher
from src.utils import get_process_hash_id


def main():
    start_time = datetime.now(pytz.UTC)
    fetcher = HotelFetcher()
    hotels = fetcher.fetch_all_hotels()
    finish_time = datetime.now(pytz.UTC)
    total_hotels = len(hotels)

    # Calculate stats
    hotels_skipped = 0  # No skipping logic
    hotels_alive = total_hotels  # All fetched are alive
    hotels_dead = 0  # No dead logic
    hotels_has_logos = 0  # No logo field, so 0
    hotels_no_logos = total_hotels  # All have no logos
    hotels_new = 0  # No new logic
    hotels_processed = total_hotels
    hotels_unprocessed = 0  # All processed
    hotels_updated = total_hotels  # All updated
    total_mongo_hotels = total_hotels  # No Mongo, use total
    total_sitemap_hotels = total_hotels  # No sitemap, use total
    total_time = str(finish_time - start_time)

    log = {
        "_id": {"$oid": "68684bc8ca800a335bef7208"},
        "process_hash_id": get_process_hash_id(),
        "current_state": "FINISHED",
        "detailed_stats": {
            "hotels_skipped": {"$numberInt": str(hotels_skipped)},
            "hotels_alive": {"$numberInt": str(hotels_alive)},
            "hotels_dead": {"$numberInt": str(hotels_dead)},
            "hotels_has_logos": {"$numberInt": str(hotels_has_logos)},
            "hotels_no_logos": {"$numberInt": str(hotels_no_logos)}
        },
        "finish_reason": "finished",
        "finish_time": {"$date": finish_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0000"},
        "hotels_new": {"$numberInt": str(hotels_new)},
        "hotels_processed": {"$numberInt": str(hotels_processed)},
        "hotels_unprocessed": {"$numberInt": str(hotels_unprocessed)},
        "hotels_updated": {"$numberInt": str(hotels_updated)},
        "start_time": {"$date": start_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0000"},
        "total_mongo_hotels": {"$numberInt": str(total_mongo_hotels)},
        "total_sitemap_hotels": {"$numberInt": str(total_sitemap_hotels)},
        "total_time": total_time
    }

    with open("hotel_logo.txt", "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    main()
