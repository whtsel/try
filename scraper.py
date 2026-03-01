import json
import uuid
import os
# Ensure your logic file is named vrt.py in the same directory
from vrt import run_scraper_and_get_data

def main():
    """
    MASTER EXECUTION: Orchestrates production-level scraping and 
    finalizes index.json for global consumption.
    """
    print("🚀 Starting Production Scrape (Max Workers: 15)...")
    
    # 1. Fetch data as a dictionary: { "id123": { "matchup": "...", ... } }
    # Note: Ensure vrt.py function is defined as: def run_scraper_and_get_data(max_workers=15):
    data_map = run_scraper_and_get_data(max_workers=15)
    
    if not data_map:
        print("⚠️ No data retrieved. Skipping update.")
        return

    # 2. Iterate correctly over Dictionary VALUES to add/check IDs
    processed_list = []
    for event_id, item in data_map.items():
        # Ensure event_id is embedded in the object for the frontend
        if not item.get('event_id'):
            item['event_id'] = event_id if event_id else str(uuid.uuid4())
        
        processed_list.append(item)

    # 3. Final Production Save
    # We save as a LIST of objects [] instead of a MAP {} 
    # if your frontend expects an array for .map() functions.
    output_path = 'index.json'
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(processed_list, f, indent=2, ensure_ascii=False)
        
        file_size = os.path.getsize(output_path) / 1024
        print(f"✅ Production API Ready: {output_path} ({len(processed_list)} items, {file_size:.2f} KB)")
    except Exception as e:
        print(f"❌ Critical Save Error: {e}")

if __name__ == "__main__":
    main()
