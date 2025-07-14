from dotenv import load_dotenv
load_dotenv()

import json
from common.mongo import get_mongo_collections
from src.hotel_fetcher import HotelFetcher

if __name__ == "__main__":
    """Main entry point for hotel metadata scraping and upload to MongoDB."""
    client, hotels_collection, _, _ = get_mongo_collections()
    fetcher = HotelFetcher(hotels_collection=hotels_collection)
    _, log_data = fetcher.fetch_all_hotels()
    # Upload hotel log directly to MongoDB (no local file)
    try:
        if log_data:
            db = client["hotel_database"]
            log_collection = db["hotels_log"]
            # Delete existing log if it exists, then insert new one
            log_collection.delete_one({"_id": log_data.get("_id")})
            log_collection.insert_one(log_data)
            print("hotel_logo.txt uploaded to MongoDB (hotels_log collection).")
        else:
            print("No log data to upload.")
    except Exception as e:
        print(f"Error uploading hotel log: {e}")
    client.close()
    print("MongoDB connection closed.")
