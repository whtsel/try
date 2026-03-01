import json
import uuid
from vrt import run_scraper_and_get_data

def main():
    # 1. Pass max_workers to the core logic
    # 2. vrt.py already saves to index.json atomically
    data = run_scraper_and_get_data(max_workers=15)
    
    # Optional: If you need to do post-processing on the returned dict:
    for event_id, details in data.items():
        if not event_id:
            # This is a fallback, though vrt.py handles this now
            new_id = str(uuid.uuid4())
            print(f"Generated fallback ID for: {details['matchup']}")

    print(f"Production Scraping Complete. {len(data)} events indexed.")

if __name__ == "__main__":
    main()
