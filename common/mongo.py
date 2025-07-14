import pymongo
import os

def get_mongo_collections(mongodb_url=None):
    """
    Connect to MongoDB and return client and main collections.
    Loads MONGODB_URL from environment if not provided (supports .env usage).
    Returns: (client, hotels_collection, plan_price_collection, plan_log_collection)
    """
    if mongodb_url is None:
        mongodb_url = os.environ.get("MONGODB_URL")
        if not mongodb_url:
            raise ValueError("MONGODB_URL environment variable is not set.")
    client = pymongo.MongoClient(mongodb_url)
    db = client["hotel_database"]
    hotels_collection = db["hotels_info"]
    plan_price_collection = db.get("plan_prices")
    plan_log_collection = db.get("plan_log")
    return client, hotels_collection, plan_price_collection, plan_log_collection 