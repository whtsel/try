import json
import uuid
from vrt import run_scraper_and_get_data

def main():
    # Production-scale workers
    data = run_scraper_and_get_data(max_workers=15)
    
    # Add unique IDs so your frontend doesn't glitch
    for item in data:
        if not item.get('event_id'):
            item['event_id'] = str(uuid.uuid4())

    with open('index.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
