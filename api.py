import os
import json
from flask import Flask, jsonify, send_file
from flask_cors import CORS 
import glob
import logging
from difflib import SequenceMatcher
from datetime import datetime
import re
import uuid # Needed for event_id fallback
from typing import List, Dict, Any

# --- Configuration ---
app = Flask(__name__) 
CORS(app, resources={r"/api/*": {"origins": "*"}}) 
DATA_DIR = os.getcwd() 

# Set up logging for the Flask app
app.logger.setLevel(logging.INFO)

# --- KJ List (Priority/Grouping Order) ---
KJ_ORDER = [
    "Premier League", 
    "LaLiga", 
    "Bundesliga", 
    "Serie A", 
    "Eredivisie", 
    "Ligue 1", 
    "Champions League", 
    "Europa League", 
    "World Cup", 
    "Afcon",
    "World Cup U17"
]
KJ_PRIORITY = {league.lower(): i for i, league in enumerate(KJ_ORDER)}
DEFAULT_PRIORITY = len(KJ_ORDER)

# --- Helper Functions (Existing) ---

def get_league_priority(competition_name):
    # ... (Keep existing get_league_priority logic) ...
    competition = competition_name.lower()
    for kj_league, priority in KJ_PRIORITY.items():
        if SequenceMatcher(None, kj_league, competition).ratio() > 0.8:
            return priority
    if 'champions league' in competition: return KJ_PRIORITY.get('champions league', DEFAULT_PRIORITY)
    if 'europa league' in competition: return KJ_PRIORITY.get('europa league', DEFAULT_PRIORITY)
    return DEFAULT_PRIORITY

def sort_fixtures_by_kj(fixtures):
    # ... (Keep existing sort_fixtures_by_kj logic) ...
    def get_sort_key(fixture):
        competition = fixture.get('competition', '')
        competition_to_sort = fixture.get('sort_competition', competition)
        priority = get_league_priority(competition_to_sort)
        time_sort = fixture.get('sort_time', datetime.min.isoformat())
        return (priority, time_sort)
    return sorted(fixtures, key=get_sort_key)

def extract_teams_from_matchup(matchup):
    # ... (Keep existing extract_teams_from_matchup logic) ...
    separators = [' – ', ' - ', ' vs ', ' VS ', ' v ', ' V ']
    for sep in separators:
        if sep in matchup:
            home, away = matchup.split(sep, 1)
            return home.strip(), away.strip()
    return matchup.strip(), matchup.strip()

def parse_time_for_sorting(date_time_str):
    # ... (Keep existing parse_time_for_sorting logic) ...
    if isinstance(date_time_str, dict) and 'parsed_datetime' in date_time_str:
        return date_time_str['parsed_datetime']
    try:
        match = re.search(r'(\d+)\s+([A-Za-z]+)\s+at\s+(\d+:\d+)', date_time_str)
        if match:
            day = int(match.group(1))
            month_str = match.group(2)
            time_str = match.group(3)
            current_year = datetime.now().year
            month_num = datetime.strptime(month_str, '%B').month 
            dt = datetime(current_year, month_num, day, *map(int, time_str.split(':')))
            return dt.isoformat()
    except Exception:
        pass
    return datetime.min.isoformat() 

# --- NEW/MODIFIED DATA LOADING ---

def load_raw_fixtures():
    """
    Loads raw fixtures data from the JSON file without enhancement/filtering.
    This simulates the input structure expected by the requested root endpoint.
    """
    try:
        today_date = datetime.now().strftime('%Y-%m-%d')
        possible_files = [
            f'today_fixtures_{today_date}.json',
            'today_fixtures.json',
            'football_fixtures_today.json'
        ]
        
        file_path = None
        for fname in possible_files:
            fpath = os.path.join(DATA_DIR, fname)
            if os.path.exists(fpath):
                file_path = fpath
                break
        
        if not file_path:
            pattern = os.path.join(DATA_DIR, '*fixtures*.json')
            all_files = glob.glob(pattern)
            if all_files:
                file_path = max(all_files, key=os.path.getctime)
                
        if file_path:
            app.logger.info(f"Loading RAW fixtures from: {os.path.basename(file_path)}")
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            app.logger.warning("No today's fixtures file found for raw loading.")
            return []
            
    except Exception as e:
        app.logger.error(f"Error loading raw fixtures: {e}")
        return []

# NOTE: The original complex 'load_today_fixtures' and 'process_and_enhance_fixture' 
# are required to support the other /api/ endpoints and are kept for full functionality.
# They are not shown here for brevity but are assumed to exist in the full file.


# --- NEW ROOT ENDPOINT (REQUIRED) ---

@app.route('/', methods=['GET'])
def get_all_fixtures_for_frontend():
    """
    Serves the root endpoint (/) by loading raw data and transforming it
    into the exact, simple array structure requested by the deepseek code block.
    """
    # NOTE: The raw fixture data must contain fields like 'id', 'competition_name', 
    # 'home_team', 'away_team', 'home_team_logo', 'away_team_logo', etc., 
    # which are expected by the requested transformation logic.
    raw_fixtures = load_raw_fixtures()
    
    # Simulating the requested structure transformation.
    processed_fixtures = []
    
    for fixture in raw_fixtures:
        
        # Determine team names and logo URLs based on raw data structure 
        # (Assuming they exist based on the frontend logic)
        
        # If the raw data is the input structure from the previous request, 
        # we need to transform it back to the expected simple keys:
        
        # Try to map complex input structure to simple output keys
        matchup_str = fixture.get("matchup", "Home – Away")
        
        # Attempt to extract team names and separate logos from 'team_logos' array
        home_team, away_team = extract_teams_from_matchup(matchup_str)
        
        home_logo_url = next((tl.get('logo_url') for tl in fixture.get('team_logos', []) 
                              if home_team.lower() in tl.get('team_name', '').lower()), "")
        away_logo_url = next((tl.get('logo_url') for tl in fixture.get('team_logos', []) 
                              if away_team.lower() in tl.get('team_name', '').lower()), "")

        processed_fixture = {
            # Use event_id from the raw data, fallback to uuid if not present
            "event_id": fixture.get("event_id", str(uuid.uuid4())),
            "competition": fixture.get("competition", ""),
            "matchup": matchup_str,
            "date_time": fixture.get("date_time", ""),
            "parsed_datetime": fixture.get("parsed_datetime", ""), # Use pre-parsed if available
            "is_live": fixture.get("is_live") is True, # Explicit check for boolean True
            "team_logos": [
                {"logo_url": home_logo_url},
                {"logo_url": away_logo_url}
            ],
            "streams": fixture.get("streams", []),
            "event_url": fixture.get("event_url", "#")
        }
        processed_fixtures.append(processed_fixture)
    
    app.logger.info(f"Root endpoint served {len(processed_fixtures)} fixtures in simple array format.")
    
    # Return direct array, no wrapper
    return jsonify(processed_fixtures)

# --- Existing Endpoints (Assumed to exist for full functionality, but not repeated here) ---

# @app.route('/api/fixtures/all', methods=['GET'])
# def get_all_fixtures():
#     # ... uses load_today_fixtures() (enhanced) ...
# @app.route('/api/fixtures/live', methods=['GET'])
# ...

# --- Run the App ---
if __name__ == '__main__':
    # Running on Mac, debug=True is useful for development.
    # Always use the SSL Bypass logic in the script (implemented by focusing on data processing rather than scraping).
    app.run(debug=True, host='0.0.0.0', port=5000)
