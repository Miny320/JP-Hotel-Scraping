# JP Hotel Scraping

This project scrapes hotel and plan data from the Ikyu.com website using their GraphQL API. It is organized into two main modules:

- `hotel_detail/`: Fetches and saves hotel metadata (IDs, names, locations, etc.)
- `plan_detail/`: Fetches detailed plan and room information for each hotel using the hotel list from `hotel_detail`

## Project Structure

```
Jp_Hotel Scraping/
  hotel_detail/
    main.py
    src/
      config.py
      hotel_fetcher.py
      utils.py
    ikyu_all_hotel.json
  plan_detail/
    main.py
    src/
      config.py
      hotel_fetcher.py
      plan_fetcher.py
      room_fetcher.py
      calendar_fetcher.py
      utils.py
```

## Setup

1. **Install Python 3.8+**
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### 1. Scrape Hotel Metadata

From the project root:

```bash
python hotel_detail/main.py
```

- This will create `hotel_detail/ikyu_all_hotel.json` with all hotel metadata.

### 2. Scrape Plan and Room Details

From the project root:

```bash
python plan_detail/main.py
```

- This will read hotel IDs from `hotel_detail/ikyu_all_hotel.json` and save detailed plan/room data to `plan_detail/ikyu_all_hotels_final.json`.

## Configuration

- Proxy, headers, and timezone settings can be adjusted in the respective `src/config.py` files.
- Batch sizes and parallelism can be tuned in the code if needed.

## Notes

- The scripts are robust to network errors and will retry failed requests.
- Make sure your proxy credentials are valid and you have network access to ikyu.com.

## License

MIT
