import json
import uuid
import os
from vrt import run_scraper_and_get_data

def main():
    print("🚀 Starting Production Scrape (Max Workers: 15)...")
    
    # Ensure vrt.py is in the same folder
    try:
        data_map = run_scraper_and_get_data(max_workers=15)
    except Exception as e:
        print(f"❌ Critical Scraper Failure: {e}")
        return

    if not data_map:
        print("⚠️ No data retrieved. Skipping update.")
        return

    # Convert Map to List for easier Frontend consumption
    processed_list = []
    for event_id, item in data_map.items():
        if not item.get('event_id'):
            item['event_id'] = event_id if event_id else str(uuid.uuid4())
        processed_list.append(item)

    output_path = 'index.json'
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(processed_list, f, indent=2, ensure_ascii=False)
        print(f"✅ Success: {len(processed_list)} items saved.")
    except Exception as e:
        print(f"❌ Save Error: {e}")

if __name__ == "__main__":
    main()
