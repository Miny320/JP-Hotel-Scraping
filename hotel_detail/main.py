import requests
import json
import time
import os
import pytz
from datetime import datetime
import hashlib
import re
from src.hotel_fetcher import HotelFetcher

def main():
    fetcher = HotelFetcher()
    fetcher.fetch_all_hotels()

if __name__ == "__main__":
    main()
