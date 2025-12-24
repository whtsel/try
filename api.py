import json
import os
from flask import Flask, jsonify
from flask_apscheduler import APScheduler
# Import your logic from vrt.py
from vrt import run_scraper_and_get_data

app = Flask(__name__)
scheduler = APScheduler()

# Configuration for 15-minute interval
class Config:
    SCHEDULER_API_ENABLED = True

app.config.from_object(Config())

def background_scrape_task():
    """The task that runs every 15 minutes."""
    print("--- 🚀 Starting Background Scrape (15 Workers) ---")
    
    # We pass 15 workers to your existing function
    # Ensure your vrt.py's run_scraper_and_get_data accepts max_workers
    data = run_scraper_and_get_data(max_workers=15)
    
    # Save results to a local file so the API stays lightning fast
    with open('index.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"--- ✅ Scrape Complete. Saved {len(data)} items. ---")

@app.route('/api/data')
def get_data():
    """Serves the latest cached data immediately."""
    if os.path.exists('index.json'):
        with open('index.json', 'r') as f:
            return jsonify(json.load(f))
    return jsonify({"error": "Data not ready yet"}), 202

if __name__ == "__main__":
    # 1. Add the job: Every 15 minutes
    scheduler.add_job(id='ScrapeTask', func=background_scrape_task, trigger='interval', minutes=15)
    
    # 2. Start the scheduler
    scheduler.start()
    
    # 3. Initial run so the API isn't empty on startup
    background_scrape_task()
    
    # 4. Run Flask (use_reloader=False prevents the task from running twice)
    app.run(host='0.0.0.0', port=5000, use_reloader=False)
