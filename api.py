import os
import json
from flask import Flask, jsonify
from flask_cors import CORS 
import glob
import logging
from difflib import SequenceMatcher
from datetime import datetime
import re
import uuid 

# --- APScheduler Imports ---
from apscheduler.schedulers.background import BackgroundScheduler
# NOTE: Assuming 'from vrt import run_scraper_and_get_data' exists in your environment.
# We will use a safe placeholder function for deployment.
def run_scraper_and_get_data():
    """Placeholder for the scraper function. Replace with actual vrt.run_scraper_and_get_data()"""
    # This will typically load data from a file during deployment for fast startup/testing.
    print("--- [SIMULATED SCRAPE] Attempting to load 'today_fixtures.json' for caching...")
    try:
        pattern = os.path.join(DATA_DIR, '*fixtures*.json')
        all_files = glob.glob(pattern)
        if all_files:
            file_path = max(all_files, key=os.path.getctime)
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except Exception as e:
        print(f"SIMULATION ERROR: Could not load dummy data: {e}")
        return []
# ---------------------------

# --- Configuration ---
app = Flask(__name__) 
CORS(app, resources={r"/api/*": {"origins": "*"}}) 
DATA_DIR = os.getcwd() 
DATA_CACHE_FILE = 'latest_data.json' # File to cache the raw scraped data

# Set up logging for the Flask app
app.logger.setLevel(logging.INFO)

# --- KJ List (Priority/Grouping Order) ---
KJ_ORDER = [
    "Premier League", "LaLiga", "Bundesliga", "Serie A", "Eredivisie", "Ligue 1", 
    "Champions League", "Europa League", "World Cup", "Afcon", "World Cup U17"
]
KJ_PRIORITY = {league.lower(): i for i, league in enumerate(KJ_ORDER)}
DEFAULT_PRIORITY = len(KJ_ORDER)

# --- Helper Functions ---

def extract_teams_from_matchup(matchup):
    # ... (Kept for completeness, remains the same) ...
    separators = [' – ', ' - ', ' vs ', ' VS ', ' v ', ' V ']
    for sep in separators:
        if sep in matchup:
            home, away = matchup.split(sep, 1)
            return home.strip(), away.strip()
    return matchup.strip(), matchup.strip()

# --- Scheduling Function (The Producer) ---

def scheduled_scrape_and_save():
    """
    Function executed by the scheduler every 30 minutes.
    It scrapes data and overwrites the local JSON cache file.
    """
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- STARTING SCHEDULED SCRAPE (30 min interval) ---")
    
    try:
        # 1. Run the core scraping function (Replace this with your actual call)
        fixtures_data = run_scraper_and_get_data()
        
        # 2. Package data with metadata
        data_to_save = {
            "timestamp": datetime.now().isoformat(),
            "fixtures": fixtures_data or [], # Cache the RAW fixtures data
            "status": "Success"
        }

        # 3. Save the result to the static JSON cache file
        with open(DATA_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Scrape SUCCESS. Saved {len(fixtures_data)} RAW fixtures to {DATA_CACHE_FILE}\n")
        
    except Exception as e:
        app.logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CRITICAL SCRAPING JOB FAILURE: {e}\n")

# --- Data Loading Function (The Consumer) ---

def load_raw_fixtures_from_cache():
    """
    Loads raw fixtures data from the cache file created by the scheduler.
    """
    if not os.path.exists(DATA_CACHE_FILE):
        app.logger.warning(f"Cache file {DATA_CACHE_FILE} not found.")
        return []
    
    try:
        with open(DATA_CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('fixtures', [])
    except Exception as e:
        app.logger.error(f"FATAL API ERROR during cache file read: {e}")
        return []

# --- ROOT ENDPOINT ---

@app.route('/', methods=['GET'])
def get_all_fixtures_for_frontend():
    """
    Serves the root endpoint (/) by loading RAW data from the cache and 
    transforming it into the exact simple array structure requested.
    """
    raw_fixtures = load_raw_fixtures_from_cache()
    
    if not raw_fixtures:
        return jsonify({
            "error": "Data file not yet created or empty.",  
            "message": "The initial scrape job is running or has not finished yet. Please try again in a few minutes."
        }), 503 
    
    processed_fixtures = []
    
    for fixture in raw_fixtures:
        
        # --- Transformation Logic ---
        matchup_str = fixture.get("matchup", "Home – Away")
        home_team, away_team = extract_teams_from_matchup(matchup_str)
        
        # Find logos in the nested 'team_logos' array
        home_logo_url = next((tl.get('logo_url') for tl in fixture.get('team_logos', []) 
                              if home_team.lower() in tl.get('team_name', '').lower()), "")
        away_logo_url = next((tl.get('logo_url') for tl in fixture.get('team_logos', []) 
                              if away_team.lower() in tl.get('team_name', '').lower()), "")

        processed_fixture = {
            "event_id": fixture.get("event_id", str(uuid.uuid4())),
            "competition": fixture.get("competition", ""),
            "matchup": matchup_str,
            "date_time": fixture.get("date_time", ""),
            "parsed_datetime": fixture.get("parsed_datetime", ""), 
            "is_live": fixture.get("is_live") is True, 
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

# --- Scheduler Startup (Gunicorn/Production Logic) ---

# Initialize the scheduler once
scheduler = BackgroundScheduler()

# This code block executes when the application is loaded by a production server 
# (e.g., Gunicorn/uWSGI). This prevents the scheduler from starting multiple times.
if __name__ != '__main__': 
    # Run the initial scrape immediately before starting the scheduler to fill the cache
    scheduled_scrape_and_save()
    
    # Add job to run every 30 minutes
    scheduler.add_job(
        scheduled_scrape_and_save, 
        'interval', 
        minutes=30, 
        id='scheduled_scrape', 
        next_run_time=datetime.now() # Run immediately on startup
    )
    
    # Start the scheduler thread
    scheduler.start()
    app.logger.info("\n✅ APScheduler started. Scrape scheduled every 30 minutes.\n")
    
# The local development server block (if __name__ == '__main__': app.run(...)) has been removed.
# To run this, you would use a command like: gunicorn api:app
