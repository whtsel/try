import json
import uuid
import os
from vrt import run_scraper_and_get_data

def main():
    print("🚀 Starting Production Scrape (Max Workers: 15)...")
    try:
        data_map = run_scraper_and_get_data(max_workers=15)
        if not data_map:
            print("⚠️ No data retrieved.")
            return

        # Transform dictionary to list for the frontend
        processed_list = []
        for event_id, item in data_map.items():
            if not item.get('event_id'):
                item['event_id'] = event_id
            processed_list.append(item)

        with open('index.json', 'w', encoding='utf-8') as f:
            json.dump(processed_list, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Success: {len(processed_list)} items exported.")
    except Exception as e:
        print(f"❌ Critical Failure: {e}")
        exit(1) # Ensure GitHub knows it failed if it actually fails

if __name__ == "__main__":
    main()
