# JP Hotel Scraping

This project scrapes hotel and plan data from the Ikyu.com website using their GraphQL API. It is organized into two main modules:

- `hotel_detail/`: Fetches and saves hotel metadata (IDs, names, locations, etc.)
- `plan_detail/`: Fetches detailed plan and room information for each hotel using the hotel list from `hotel_detail`

## Project Structure

```
ikyu_scraper_new/
  hotel_detail/
    main.py
    src/
      hotel_fetcher.py
  plan_detail/
    main.py
    src/
      calendar_fetcher.py
      hotel_fetcher.py
      plan_fetcher.py
      room_fetcher.py
```

## Setup

1. **Install Python 3.8+**
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure Environment Variables:**
   - Create a `.env` file in the project root (or set environment variables directly).
   - At minimum, set your MongoDB connection string:
     ```env
     MONGODB_URL=mongodb+srv://<username>:<password>@<cluster-url>/hotel_database?retryWrites=true&w=majority
     ```
   - You can also set proxy, headers, and other settings as needed.

## Usage

### 1. Scrape Hotel Metadata

From the project root:

```bash
python hotel_detail/main.py
```

- This will create `hotel_detail/ikyu_all_hotel.json` with all hotel metadata and upload logs to MongoDB.

### 2. Scrape Plan and Room Details

From the project root:

```bash
python plan_detail/main.py
```

- This will read hotel IDs from `hotel_detail/ikyu_all_hotel.json` and save detailed plan/room data to `plan_detail/ikyu_all_hotels_final.json` and MongoDB.

## Configuration

- All sensitive information (like MongoDB credentials) must be set via environment variables or a `.env` file. **Do not hardcode credentials in the code.**
- Proxy, headers, and timezone settings can be adjusted in the respective `src/config.py` files.
- **Batch size for room fetching is set to 20** for improved performance (see `plan_detail/src/hotel_fetcher.py`).

## Improvements

- Improved error handling and logging for robustness and easier debugging.
- All configuration is centralized and loaded from environment variables or config files.
- No sensitive information is hardcoded in the codebase.

## Notes

- The scripts are robust to network errors and will retry failed requests.
- Make sure your proxy credentials are valid and you have network access to ikyu.com.

## License

MIT
