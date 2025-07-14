import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from src.hotel_fetcher import run_all_hotels

if __name__ == "__main__":
    """Main entry point for plan and room detail scraping."""
    run_all_hotels()
