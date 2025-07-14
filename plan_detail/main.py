import os
import sys
from dotenv import load_dotenv
load_dotenv()

from src.hotel_fetcher import run_all_hotels

if __name__ == "__main__":
    """Main entry point for plan and room detail scraping."""
    run_all_hotels()
