import json
import uuid
import os
import sys

# MASTER ARCHITECT FIX: Force Python to look in the current directory for vrt.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from vrt import run_scraper_and_get_data
except ImportError as e:
    print(f"❌ CRITICAL: Could not find vrt.py in the repository. Error: {e}")
    sys.exit(1)

def main():
    print("🚀 Starting Production Scrape via scraper.py...")
    
    try:
        # 1. Fetch data from the vrt logic engine
        data_map = run_scraper_and_get_data(max_workers=15)
        
        if not data_map:
            print("⚠️ No data returned. Check vrt.py logs.")
            return

        # 2. Transform Map to List for Frontend Consumption
        processed_list = []
        for eid, item in data_map.items():
            if not item.get('event_id'):
                item['event_id'] = eid
            processed_list.append(item)

        # 3. Final Production Save
        output_path = 'index.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(processed_list, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Success: {len(processed_list)} items exported to {output_path}")

    except Exception as e:
        print(f"❌ Execution Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
