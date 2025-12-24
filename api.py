import json
import uuid
import os
from datetime import datetime
from vrt import run_scraper_and_get_data

def extract_teams(matchup):
    # Your helper function from api.py
    separators = [' – ', ' - ', ' vs ', ' VS ', ' v ', ' V ']
    for sep in separators:
        if sep in matchup:
            home, away = matchup.split(sep, 1)
            return home.strip(), away.strip()
    return matchup.strip(), matchup.strip()

def main():
    print(f"[{datetime.now()}] Starting Scrape...")
    
    # 1. Run your vrt.py logic
    raw_fixtures = run_scraper_and_get_data() or []
    
    processed_fixtures = []
    
    # 2. Apply your transformation logic from api.py
    for fixture in raw_fixtures:
        matchup_str = fixture.get("matchup", "Home – Away")
        home_team, away_team = extract_teams(matchup_str)
        
        # Extract logos as you did in api.py
        logos = fixture.get('team_logos', [])
        home_logo = next((tl.get('logo_url') for tl in logos if home_team.lower() in tl.get('team_name', '').lower()), "")
        away_logo = next((tl.get('logo_url') for tl in logos if away_team.lower() in tl.get('team_name', '').lower()), "")

        processed_fixtures.append({
            "event_id": fixture.get("event_id") or str(uuid.uuid4()),
            "competition": fixture.get("competition", ""),
            "matchup": matchup_str,
            "date_time": fixture.get("date_time", ""),
            "is_live": fixture.get("is_live") is True,
            "team_logos": [{"logo_url": home_logo}, {"logo_url": away_logo}],
            "streams": fixture.get("streams", []),
            "event_url": fixture.get("event_url", "#")
        })

    # 3. Save as index.json (This is your Static API endpoint)
    with open('index.json', 'w', encoding='utf-8') as f:
        json.dump(processed_fixtures, f, indent=2, ensure_ascii=False)
    
    print(f"Update Complete. {len(processed_fixtures)} fixtures saved.")

if __name__ == "__main__":
    main()
