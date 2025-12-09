from flask import Flask, jsonify
import json
import os
from vrt import run_scraper_and_get_data 
from datetime import datetime

# --- APScheduler Imports ---
from apscheduler.schedulers.background import BackgroundScheduler
# ---------------------------

# Define the file where the latest scraped data will be saved
DATA_FILE = 'latest_data.json' 

# 💡 Define the Flask application instance named 'app'
app = Flask(__name__)

# --- Scheduling Function (Runs the scrape and saves the file) ---

def scheduled_scrape_and_save():
    """
    Function executed by the scheduler every 30 minutes.
    It scrapes data and overwrites the local JSON file.
    """
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- STARTING SCHEDULED SCRAPE (30 min interval) ---")
    
    try:
        # 1. Run the core scraping function from vrt.py
        fixtures_data = run_scraper_and_get_data()
        
        # 2. Package data with metadata
        data_to_save = {
            "timestamp": datetime.now().isoformat(),
            "fixtures": fixtures_data or [],
            "status": "Success"
        }

        # 3. Save the result to the static JSON file
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Scrape SUCCESS. Saved {len(fixtures_data)} fixtures to {DATA_FILE}\n")
        
    except Exception as e:
        # Crucial for debugging when the job fails silently
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CRITICAL SCRAPING JOB FAILURE: {e}\n")

# --- Flask Endpoint (Reads the file) ---

@app.route('/', methods=['GET'])
def get_scraper_data():
    """
    API endpoint that reads the latest pre-scraped data from a file.
    """
    print("API request received. Reading pre-scraped data...")
    
    if not os.path.exists(DATA_FILE):
        return jsonify({
            "error": "Data file not yet created.", 
            "message": "The initial scrape job is running or has not finished yet. Please try again in a few minutes."
        }), 503 
        
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Return the 'fixtures' list
        return jsonify(data.get('fixtures', data)) 
        
    except Exception as e:
        print(f"FATAL API ERROR during file read: {e}")
        return jsonify({"error": "Internal server error during file read.", "details": str(e)}), 500

# --- Scheduler Startup ---

# We only start the scheduler if we are running in the main Gunicorn process 
# to avoid running it multiple times across workers.
if __name__ != '__main__': # This block runs when Gunicorn starts
    # Initialize and start the scheduler
    scheduler = BackgroundScheduler()
    
    # Add job to run immediately upon startup (if needed) and then every 30 minutes
    # NOTE: You can remove the 'seconds=5' if you want it to run exactly on the 30-minute mark.
    scheduler.add_job(
        scheduled_scrape_and_save, 
        'interval', 
        minutes=30, 
        id='scheduled_scrape', 
        next_run_time=datetime.now() # Run immediately on startup
    )
    
    # Run the initial scrape immediately before starting the scheduler
    scheduled_scrape_and_save()
    
    # Start the scheduler thread
    scheduler.start()
    print(f"\n✅ APScheduler started. Scrape scheduled every 30 minutes.\n")

# Local testing
if __name__ == '__main__':
    # Run the initial scrape immediately
    scheduled_scrape_and_save()
    
    # Start the scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(scheduled_scrape_and_save, 'interval', minutes=30, id='local_scrape')
    scheduler.start()
    
    # Run the Flask app
    app.run(debug=True)
