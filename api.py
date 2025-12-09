import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import urllib3
import re
from urllib.parse import urljoin
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from queue import Queue
import signal
from difflib import SequenceMatcher

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Configuration for Priority and Filtering ---

# 1. League Priority Order (as requested)
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

# Create a mapping for quick lookup of priority
KJ_PRIORITY = {league.lower(): i for i, league in enumerate(KJ_ORDER)}
# A high number for leagues not in the priority list
DEFAULT_PRIORITY = len(KJ_ORDER) 

# --- Helper Functions for Sorting and Filtering ---

def get_league_priority(competition_name):
    """Returns the priority index for a competition, lower is higher priority."""
    competition = competition_name.lower()
    
    # Check for fuzzy or substring match
    for kj_league, priority in KJ_PRIORITY.items():
        if SequenceMatcher(None, kj_league, competition).ratio() > 0.8 or kj_league in competition or competition in kj_league:
            return priority
    
    # Check for common keyword matches
    if 'champions' in competition: return KJ_PRIORITY.get('champions league', DEFAULT_PRIORITY)
    if 'europa' in competition: return KJ_PRIORITY.get('europa league', DEFAULT_PRIORITY)
    if 'world cup' in competition: return KJ_PRIORITY.get('world cup', DEFAULT_PRIORITY)
    if 'afcon' in competition or 'africa cup' in competition: return KJ_PRIORITY.get('afcon', DEFAULT_PRIORITY)
    
    return DEFAULT_PRIORITY

def sort_by_league_priority(fixtures):
    """Sorts fixtures based on the custom KJ_ORDER list."""
    # We sort primarily by league priority, and secondarily by the parsed datetime
    def sort_key(fixture):
        priority = get_league_priority(fixture.get('competition', ''))
        # Use the parsed_datetime for secondary sorting (time order within a league)
        time_sort = fixture.get('parsed_datetime', datetime.min.isoformat())
        return (priority, time_sort)
    
    return sorted(fixtures, key=sort_key)

def filter_by_logo_presence(fixtures):
    """Filters out fixtures that do not have team logos."""
    filtered = []
    for fixture in fixtures:
        logos = fixture.get('team_logos', [])
        # A fixture is considered to have logos if the 'team_logos' list 
        # is present and contains at least two entries (Home and Away)
        if len(logos) >= 2:
            filtered.append(fixture)
            
    print(f"✅ Filtered {len(fixtures) - len(filtered)} games without logos.")
    return filtered

# --- BroadcastScraper Class ---

class BroadcastScraper:
    # Set max_workers to 3 for a balance of speed and stability on the free plan.
    def __init__(self, base_url="https://livetv.sx", max_workers=3):
        self.base_url = base_url
        self.max_workers = max_workers
        self.session = requests.Session()
        # Explicitly set verify=False for SSL Bypass logic (as requested)
        self.session.verify = False 
        self.session.headers.update({
            # Updated User-Agent for Mac (as requested)
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })
        
        # Thread-safe counters
        self.stats_lock = threading.Lock()
        self.successful_requests = 0
        self.failed_requests = 0
        
        # Progress tracking
        self.progress_lock = threading.Lock()
        self.completed_tasks = 0
        self.total_tasks = 0
        
    def _parse_broadcast_item(self, table):
        """
        Parses a single fixture table (table with cellpadding="1").
        """
        fixture_data = {}
        
        try:
            # Find the link tag in this table
            link_tag = table.find('a', class_='live')
            if not link_tag:
                link_tag = table.find('a', class_='bottomgray')
            
            if not link_tag:
                return None
            
            # 1. Extract Matchup and Stream Link
            matchup_text = link_tag.get_text(strip=True)
            fixture_data['matchup'] = matchup_text
            
            stream_href = link_tag.get('href')
            if stream_href:
                if stream_href.startswith('/'):
                    fixture_data['event_url'] = self.base_url + stream_href
                    # Extract event ID from URL
                    match = re.search(r'/eventinfo/(\d+)', stream_href)
                    if match:
                        fixture_data['event_id'] = match.group(1)
                else:
                    fixture_data['event_url'] = stream_href
            
            # 2. Extract Date, Time, and Competition
            evdesc_span = table.find('span', class_='evdesc')
            if evdesc_span:
                desc_text = evdesc_span.get_text(separator=' ', strip=True)
                
                # Split by newline if present
                if '\n' in evdesc_span.text:
                    desc_parts = [p.strip() for p in evdesc_span.get_text('\n').split('\n') if p.strip()]
                else:
                    desc_parts = [desc_text]
                
                if desc_parts:
                    date_time_text = desc_parts[0]
                    fixture_data['date_time'] = date_time_text
                    
                    if len(desc_parts) >= 2:
                        competition_text = desc_parts[1].strip('()')
                        fixture_data['competition'] = competition_text
                    
                    # 3. Parse Date/Time - Store as datetime object for filtering
                    try:
                        # Handle format: "3 December at 1:00"
                        month_pattern = r'(\d+)\s+([A-Za-z]+)\s+at\s+(\d+:\d+)'
                        match = re.search(month_pattern, date_time_text)
                        
                        if match:
                            # Use full month name for parsing, then replace with current year
                            date_part = f"{match.group(1)} {match.group(2)} at {match.group(3)}"
                            current_year = datetime.now().year
                            parsed_date = datetime.strptime(date_part, '%d %B at %H:%M').replace(year=current_year)
                            fixture_data['parsed_datetime'] = parsed_date.isoformat()
                            fixture_data['datetime_obj'] = parsed_date  # Store datetime object
                    except Exception:
                        fixture_data['parsed_datetime'] = None
                        fixture_data['datetime_obj'] = None
            
            # 4. Extract Logo/Country Info
            img_tag = table.find('img', alt=True)
            if img_tag:
                fixture_data['logo_alt'] = img_tag['alt']
            
            # 5. Check if it's a live match
            live_img = table.find('img', src=lambda x: x and 'live.gif' in x)
            fixture_data['is_live'] = live_img is not None
            
            return fixture_data
                
        except Exception:
            return None
    
    def get_fixtures_for_sport(self, sport_url):
        """
        Navigates to the sport page and extracts fixtures for TODAY only.
        """
        today_fixtures = []
        
        try:
            response = self.session.get(sport_url, timeout=15)
            response.raise_for_status()
            
            with self.stats_lock:
                self.successful_requests += 1
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Get today's date for filtering
            today = datetime.now().date()
            today_day = datetime.now().day
            
            # Find all fixture tables
            fixture_tables = soup.find_all('table', {'cellpadding': '1', 'cellspacing': '2'})
            
            print(f"📋 Found {len(fixture_tables)} potential fixture tables")
            
            # Parse all fixtures and filter for today
            for table in fixture_tables:
                fixture = self._parse_broadcast_item(table)
                if fixture:
                    # Check if fixture is for today
                    is_today = False
                    
                    # Method 1: Check if we have a datetime object and compare dates
                    if fixture.get('datetime_obj'):
                        fixture_date = fixture['datetime_obj'].date()
                        if fixture_date == today:
                            is_today = True
                    # Method 2: Check date string for today's day number
                    elif fixture.get('date_time'):
                        date_str = fixture['date_time']
                        # Check if the date string contains today's day
                        if re.search(rf'^{today_day}\s+[A-Za-z]+', date_str) or \
                           re.search(rf'\b{today_day}\s+[A-Za-z]+', date_str):
                            is_today = True
                    
                    # Only add if it's for today
                    if is_today:
                        # Check if this is a duplicate
                        is_duplicate = any(
                            f.get('event_id') == fixture.get('event_id') and 
                            f.get('event_id') is not None
                            for f in today_fixtures
                        )
                        
                        if not is_duplicate:
                            today_fixtures.append(fixture)
            
            print(f"✅ Parsed {len(today_fixtures)} fixtures for today")
            # Clear datetime object before saving to JSON later
            for f in today_fixtures:
                if 'datetime_obj' in f:
                    del f['datetime_obj']
                    
            return [], today_fixtures
            
        except requests.exceptions.RequestException as e:
            with self.stats_lock:
                self.failed_requests += 1
            print(f"❌ Request failed: {e}")
            return [], []
        except Exception as e:
            print(f"❌ Error parsing fixtures: {e}")
            return [], []
    
    def scrape_team_logos(self, event_url):
        """
        Scrape team logos from an event page. (Legacy/stand-alone version)
        """
        # This function is redundant, using get_event_details_sequential_streams instead
        pass
    
    def _parse_stream_table(self, table):
        """
        Parse a single stream table (class lnktbj) to extract stream details.
        """
        try:
            stream_data = {}
            
            # Find all table cells
            cells = table.find_all('td')
            if len(cells) < 7:
                return None
            
            # 1. Language/flag info (first cell)
            flag_img = cells[0].find('img')
            if flag_img:
                stream_data['language'] = flag_img.get('title', '')
                stream_data['flag_src'] = flag_img.get('src', '')
                if stream_data['flag_src'].startswith('//'):
                    stream_data['flag_src'] = 'https:' + stream_data['flag_src']
            
            # 2. Bitrate (second cell)
            bitrate_cell = cells[1]
            stream_data['bitrate'] = bitrate_cell.get('title', '')
            
            # 3. Rating information (cells 2-4)
            rating_div = table.find('div', id=lambda x: x and x.startswith('rali'))
            if rating_div:
                stream_data['rating'] = rating_div.get_text(strip=True)
                stream_data['rating_color'] = rating_div.get('style', '')
            
            # 4. Stream link (cell 5 - play button)
            play_link = cells[5].find('a') if len(cells) > 5 else None
            if play_link:
                stream_url = play_link.get('href', '')
                if stream_url:
                    if stream_url.startswith('//'):
                        stream_url = 'https:' + stream_url
                    elif stream_url.startswith('/'):
                        stream_url = urljoin(self.base_url, stream_url)
                    
                    stream_data['stream_url'] = stream_url
                    stream_data['stream_title'] = play_link.get('title', '')
            
            # 5. Stream type/description (last cell)
            if len(cells) > 6:
                type_cell = cells[6]
                type_span = type_cell.find('span')
                if type_span:
                    stream_data['stream_type'] = type_span.get_text(strip=True)
                else:
                    stream_data['stream_type'] = type_cell.get_text(strip=True)
            
            return stream_data
            
        except Exception:
            return None
    
    def get_event_details_sequential_streams(self, event_url):
        """
        Get comprehensive event details with sequential stream parsing.
        """
        try:
            response = self.session.get(event_url, timeout=15)
            response.raise_for_status()
            
            with self.stats_lock:
                self.successful_requests += 1
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            event_data = {
                'event_url': event_url,
                'team_logos': [],
                'streams': [],
                'starting_lineups': {},
                'match_info': {}
            }
            
            # 1. Extract team logos
            logo_images = soup.find_all('img', itemprop='image', alt=True)
            for img in logo_images:
                logo_url = img.get('src', '')
                if logo_url:
                    if logo_url.startswith('//'):
                        logo_url = 'https:' + logo_url
                    elif logo_url.startswith('/'):
                        logo_url = urljoin(self.base_url, logo_url)
                    
                    event_data['team_logos'].append({
                        'team_name': img.get('alt', '').strip(),
                        'logo_url': logo_url,
                        'style': img.get('style', '')
                    })
            
            # 2. Extract stream links from the links_block
            links_block = soup.find('div', id='links_block')
            if links_block:
                # Find all stream tables (class lnktbj)
                stream_tables = links_block.find_all('table', class_='lnktbj')
                
                # **SEQUENTIAL STREAM PARSING:** Use a simple loop to minimize memory usage
                for table in stream_tables:
                    stream_data = self._parse_stream_table(table)
                    if stream_data:
                        event_data['streams'].append(stream_data)
            
            return event_data
            
        except Exception:
            with self.stats_lock:
                self.failed_requests += 1
            return None
    
    def process_fixture_concurrent(self, fixture):
        """
        Process a single fixture concurrently (team logos + event details).
        This runs using one of the 3 main workers.
        """
        try:
            event_url = fixture.get('event_url')
            
            if event_url:
                # Call the sequential stream parsing function
                detailed_info = self.get_event_details_sequential_streams(event_url)
                
                if detailed_info:
                    # Add logos to fixture data
                    if detailed_info.get('team_logos'):
                        fixture['team_logos'] = detailed_info['team_logos']
                    
                    # Add streams to fixture data
                    if detailed_info.get('streams'):
                        fixture['streams'] = detailed_info['streams']
                
                # Update progress
                with self.progress_lock:
                    self.completed_tasks += 1
                    self._show_progress()
                
            return fixture
            
        except Exception as e:
            # print(f"\n⚠️ Error processing fixture: {e}") # Suppress verbose error output during concurrency
            with self.progress_lock:
                self.completed_tasks += 1
                self._show_progress()
            return fixture
    
    def _show_progress(self):
        """Display a progress bar"""
        if self.total_tasks == 0:
            return
            
        percent = float(self.completed_tasks) / self.total_tasks
        bar_length = 40
        arrow = '█' * int(round(percent * bar_length))
        spaces = '░' * (bar_length - len(arrow))
        
        sys.stdout.write(f"\r🔄 Processing: [{arrow}{spaces}] {int(round(percent * 100))}% ({self.completed_tasks}/{self.total_tasks})")
        sys.stdout.flush()
    
    def process_all_fixtures_concurrent(self, fixtures):
        """
        Process all fixtures concurrently using 3 ThreadPoolExecutor workers.
        """
        if not fixtures:
            return fixtures
        
        # Initialize progress tracking
        with self.progress_lock:
            self.completed_tasks = 0
            self.total_tasks = len(fixtures)
        
        print(f"\n🚀 Starting concurrent processing of {len(fixtures)} fixtures with {self.max_workers} workers...")
        
        # Process fixtures concurrently
        ordered_results = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            futures = {executor.submit(self.process_fixture_concurrent, fixture): i 
                      for i, fixture in enumerate(fixtures)}
            
            # Process results as they complete
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    result = future.result(timeout=30)
                    ordered_results[idx] = result
                except Exception:
                    # If failed, use the original fixture to prevent data loss
                    ordered_results[idx] = fixtures[idx]

        # Reconstruct the list in the original order
        processed_fixtures = [ordered_results[i] for i in sorted(ordered_results.keys())]
        
        # Clear progress line
        sys.stdout.write("\r" + " " * 80 + "\r")
        
        return processed_fixtures
    
    def save_to_json(self, data, filename):
        """Save scraped data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

# --- Main Scraper Execution ---

def main():
    # Create scraper with 3 workers
    scraper = BroadcastScraper(max_workers=3)
    
    # The full URL for Football fixtures
    sport_url = "https://livetv.sx/enx/allupcomingsports/1/"
    
    today_date = datetime.now().strftime('%d %B %Y')
    print(f"🔍 Fetching TODAY'S football fixtures ({today_date})...")
    print(f"⚡ Using {scraper.max_workers} concurrent workers for fixtures")
    
    start_time = time.time()
    
    # Step 1: Get TODAY'S fixtures only
    top_matches, today_fixtures = scraper.get_fixtures_for_sport(sport_url)
    
    if not today_fixtures:
        print(f"\n❌ No fixtures found for today ({today_date})")
        return
    
    print(f"\n✅ Found {len(today_fixtures)} fixtures for today")
    
    # Step 2: Process all fixtures concurrently (team logos + event details)
    fixtures_with_details = scraper.process_all_fixtures_concurrent(today_fixtures)
    
    # -------------------------------------------------------------------
    ## Applying User Requirements: Filtering and Sorting
    # -------------------------------------------------------------------
    
    # 3a. Filter out games without team logos
    fixtures_logo_filtered = filter_by_logo_presence(fixtures_with_details)
    
    if not fixtures_logo_filtered:
        print("\n❌ All fixtures were filtered out due to missing team logos. Nothing to save.")
        return
        
    # 3b. Sort based on the specified league priority
    final_sorted_fixtures = sort_by_league_priority(fixtures_logo_filtered)
    
    print(f"✅ Final data count after filtering and sorting: {len(final_sorted_fixtures)}")
    
    # Step 4: Save results with today's date in filename
    today_filename = datetime.now().strftime('%Y-%m-%d')
    filename = f'today_fixtures_{today_filename}.json'
    
    # Save the final sorted and filtered fixtures
    scraper.save_to_json(final_sorted_fixtures, filename)
    
    # -------------------------------------------------------------------
    
    # Calculate statistics
    processing_time = time.time() - start_time
    
    fixtures_with_logos_count = len(final_sorted_fixtures) # This is the final count
    fixtures_with_streams_count = sum(1 for f in final_sorted_fixtures if f.get('streams'))
    live_fixtures_count = sum(1 for f in final_sorted_fixtures if f.get('is_live'))
    
    print("\n" + "=" * 60)
    print("📊 TODAY'S FOOTBALL FIXTURES - SUMMARY")
    print("=" * 60)
    print(f"📅 Date: {today_date}")
    print(f"⏱️  Total time: {processing_time:.2f} seconds")
    print(f"📈 Successful requests: {scraper.successful_requests}")
    print(f"❌ Failed requests: {scraper.failed_requests}")
    print(f"📊 Total matches (Filtered & Sorted): {len(final_sorted_fixtures)}")
    print(f"🔴 Live now: {live_fixtures_count}")
    print(f"🏆 With team logos: {fixtures_with_logos_count}")
    print(f"📺 With stream links: {fixtures_with_streams_count}")
    print(f"💾 Saved to: {filename}")
    print("=" * 60)
    
    # Show today's matches
    print("\n🎯 TODAY'S MATCHES (Top 10 Sorted by Priority):")
    print("-" * 50)
    
    for i, fixture in enumerate(final_sorted_fixtures[:10]):  # Show first 10 matches
        live_indicator = " 🔴 LIVE" if fixture.get('is_live') else ""
        competition_name = fixture.get('competition', 'N/A')
        priority = get_league_priority(competition_name)
        priority_label = next((k for k, v in KJ_PRIORITY.items() if v == priority), 'Other')
        
        print(f"{i+1}. [{priority_label.upper()}] {fixture.get('matchup')}{live_indicator}")
        print(f"   ⏰ {fixture.get('date_time', 'N/A')}")
        
        if fixture.get('team_logos'):
            team_names = [logo.get('team_name', 'Unknown') for logo in fixture['team_logos']]
            if team_names:
                print(f"   👥 Teams: {', '.join(team_names[:2])}")
        
        if fixture.get('streams'):
            languages = list(set([s.get('language', '') for s in fixture['streams'] if s.get('language')]))
            if languages:
                print(f"   🌍 Available in: {', '.join(languages[:2])}{'...' if len(languages) > 2 else ''}")
        
        print()  # Empty line between matches
    
    if len(final_sorted_fixtures) > 10:
        print(f"... and {len(final_sorted_fixtures) - 10} more matches")
    
    print("=" * 60)
    print(f"✅ Done! All data saved to '{filename}'")
    print(f"⚡ Processed {len(final_sorted_fixtures)} fixtures in {processing_time:.2f}s "
          f"({len(final_sorted_fixtures)/processing_time:.2f} fixtures/sec)")
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Process interrupted by user. Exiting...")
        sys.exit(0)
