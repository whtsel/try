import json
import uuid
import os
import sys

# Ensure local imports work in GitHub Actions
# This specifically targets the root directory where vrt.py resides
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

try:
    from vrt import run_scraper_and_get_data
except ImportError as e:
    print(f"❌ Critical Error: Could not find vrt.py in {BASE_DIR}. Error: {e}")
    sys.exit(1)

def main():
    print("🚀 Starting Views Project Production Scrape...")
    
    try:
        # Pass max_workers=15 for high-speed concurrent detail fetching
        # This will now include lineups and league tables as requested
        data_map = run_scraper_and_get_data(max_workers=15)
        
        if not data_map:
            print("⚠️ Warning: No data retrieved from the scraper.")
            # We exit with 0 to prevent GitHub Action from failing if it's just a "no games today" scenario
            sys.exit(0)

        # Logic Check: Handle both Dictionary and List returns from vrt.py
        if isinstance(data_map, dict):
            processed_list = list(data_map.values())
        else:
            processed_list = data_map

        # Define the absolute path for index.json to ensure it stays in the repo root
        output_path = os.path.join(BASE_DIR, 'index.json')

        # FINAL PRODUCTION WRITE
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(processed_list, f, indent=2, ensure_ascii=False)
        
        print("-" * 30)
        print(f"✅ PRODUCTION SUCCESS")
        print(f"📦 File: index.json")
        print(f"🔢 Items: {len(processed_list)}")
        print(f"🕒 Timestamp: {os.popen('date').read().strip()}")
        print("-" * 30)

    except Exception as e:
        print(f"❌ Scraper Execution Error: {e}")
        # Exit 1 triggers the GitHub Action failure notification
        sys.exit(1)

if __name__ == "__main__":
    main()
