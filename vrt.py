import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import urllib3
import re
from urllib.parse import urljoin
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Suppress SSL warnings for production stability
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class BroadcastScraper:
    def __init__(self, base_url="https://livetv.sx", max_workers=15):
        self.base_url = base_url
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.verify = False 
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        })
        
        self.stats_lock = threading.Lock()
        self.successful_requests = 0
        self.failed_requests = 0
        
    def _parse_broadcast_item(self, table):
        fixture_data = {}
        try:
            link_tag = table.find('a', class_='live') or table.find('a', class_='bottomgray')
            if not link_tag: return None
            
            fixture_data['matchup'] = link_tag.get_text(strip=True)
            stream_href = link_tag.get('href')
            if stream_href:
                fixture_data['event_url'] = urljoin(self.base_url, stream_href)
                match = re.search(r'/eventinfo/(\d+)', stream_href)
                if match: fixture_data['event_id'] = match.group(1)
            
            evdesc_span = table.find('span', class_='evdesc')
            if evdesc_span:
                desc_parts = [p.strip() for p in evdesc_span.get_text('\n').split('\n') if p.strip()]
                if desc_parts:
                    fixture_data['date_time'] = desc_parts[0]
                    if len(desc_parts) >= 2:
                        fixture_data['competition'] = desc_parts[1].strip('()')
                    
                    try:
                        month_pattern = r'(\d+)\s+([A-Za-z]+)\s+at\s+(\d+:\d+)'
                        match = re.search(month_pattern, desc_parts[0])
                        if match:
                            date_part = f"{match.group(1)} {match.group(2)} at {match.group(3)}"
                            parsed_date = datetime.strptime(date_part, '%d %B at %H:%M').replace(year=datetime.now().year)
                            fixture_data['parsed_datetime'] = parsed_date.isoformat()
                    except:
                        fixture_data['parsed_datetime'] = None

            img_tag = table.find('img', alt=True)
            if img_tag: fixture_data['logo_alt'] = img_tag['alt']
            
            live_img = table.find('img', src=lambda x: x and 'live.gif' in x)
            fixture_data['is_live'] = live_img is not None
            
            return fixture_data
        except:
            return None

    def get_fixtures_for_sport(self, sport_url):
        today_fixtures = []
        try:
            response = self.session.get(sport_url, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')
            today_day = datetime.now().day
            fixture_tables = soup.find_all('table', {'cellpadding': '1', 'cellspacing': '2'})
            
            for table in fixture_tables:
                fixture = self._parse_broadcast_item(table)
                if fixture and fixture.get('date_time'):
                    # Match day logic for "Today"
                    if re.search(rf'\b{today_day}\s+[A-Za-z]+', fixture['date_time']):
                        today_fixtures.append(fixture)
            
            return [], today_fixtures
        except:
            return [], []

    def _parse_stream_table(self, table):
        try:
            cells = table.find_all('td')
            if len(cells) < 7: return None
            
            stream_data = {}
            flag_img = cells[0].find('img')
            if flag_img:
                stream_data['language'] = flag_img.get('title', '')
                stream_data['flag_src'] = urljoin(self.base_url, flag_img.get('src', ''))
            
            stream_data['bitrate'] = cells[1].get('title', '')
            play_link = cells[5].find('a')
            if play_link:
                stream_data['stream_url'] = urljoin(self.base_url, play_link.get('href', ''))
                stream_data['stream_title'] = play_link.get('title', '')
            
            type_cell = cells[6]
            stream_data['stream_type'] = type_cell.get_text(strip=True)
            return stream_data
        except:
            return None

    def get_event_details_concurrent(self, event_url):
        try:
            response = self.session.get(event_url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            event_data = {'team_logos': [], 'streams': []}
            
            # Logos
            for img in soup.find_all('img', itemprop='image', alt=True):
                event_data['team_logos'].append({
                    'team_name': img.get('alt', '').strip(),
                    'logo_url': urljoin(self.base_url, img.get('src', ''))
                })
            
            # Streams
            links_block = soup.find('div', id='links_block')
            if links_block:
                stream_tables = links_block.find_all('table', class_='lnktbj')
                for table in stream_tables:
                    s_data = self._parse_stream_table(table)
                    if s_data: event_data['streams'].append(s_data)
            
            return event_data
        except:
            return None

    def process_fixture_concurrent(self, fixture):
        event_url = fixture.get('event_url')
        if event_url:
            details = self.get_event_details_concurrent(event_url)
            if details:
                fixture['team_logos'] = details.get('team_logos', [])
                fixture['streams'] = details.get('streams', [])
        return fixture

    def process_all_fixtures_concurrent(self, fixtures):
        if not fixtures: return []
        processed = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self.process_fixture_concurrent, f) for f in fixtures]
            for future in as_completed(futures):
                try:
                    processed.append(future.result(timeout=20))
                except:
                    continue
        return processed

# --- PRODUCTION EXPORT ---
def run_scraper_and_get_data(max_workers=15):
    scraper = BroadcastScraper(max_workers=max_workers) 
    sport_url = "https://livetv.sx/enx/allupcomingsports/1/"
    _, today_fixtures = scraper.get_fixtures_for_sport(sport_url)
    
    if not today_fixtures:
        return []
        
    return scraper.process_all_fixtures_concurrent(today_fixtures)
