import json
import uuid
import os
import sys

# Ensure local imports work in GitHub Actions
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from vrt import run_scraper_and_get_data
except ImportError as e:
    print(f"❌ Could not find vrt.py: {e}")
    sys.exit(1)

def main():
    print("🚀 Starting Production Scrape...")
    try:
        data_map = run_scraper_and_get_data(max_workers=15)
        
        if not data_map:
            print("⚠️ No data retrieved.")
            return

        # Convert Dictionary to List for Production API Consumption
        processed_list = list(data_map.values())

        with open('index.json', 'w', encoding='utf-8') as f:
            json.dump(processed_list, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Success: {len(processed_list)} items saved to index.json")
    except Exception as e:
        print(f"❌ Scraper Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
