import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import urllib3
import re
from urllib.parse import urljoin
import threading
import os
import uuid
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class BroadcastScraper:
    def __init__(self, base_url="https://livetv.sx", max_workers=15):
        self.base_url = base_url
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.verify = False 
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })

    def _generate_stable_id(self, matchup_str):
        return hashlib.md5(matchup_str.encode()).hexdigest()[:12]

    def _parse_broadcast_item(self, table):
        try:
            link_tag = table.find('a', class_='live') or table.find('a', class_='bottomgray')
            if not link_tag: return None
            matchup = link_tag.get_text(strip=True)
            fixture_data = {'matchup': matchup}
            stream_href = link_tag.get('href', '')
            if stream_href:
                fixture_data['event_url'] = urljoin(self.base_url, stream_href)
                match = re.search(r'/eventinfo/(\d+)', stream_href)
                fixture_data['event_id'] = match.group(1) if match else self._generate_stable_id(matchup)
            
            evdesc_span = table.find('span', class_='evdesc')
            if evdesc_span:
                desc_parts = [p.strip() for p in evdesc_span.get_text('\n').split('\n') if p.strip()]
                if desc_parts:
                    fixture_data['date_time'] = desc_parts[0]
                    if len(desc_parts) >= 2: fixture_data['competition'] = desc_parts[1].strip('()')
                    try:
                        m = re.search(r'(\d+)\s+([A-Za-z]+)\s+at\s+(\d+:\d+)', desc_parts[0])
                        if m:
                            date_part = f"{m.group(1)} {m.group(2)} at {m.group(3)}"
                            parsed_date = datetime.strptime(date_part, '%d %B at %H:%M').replace(year=datetime.now().year)
                            fixture_data['parsed_datetime'] = parsed_date.isoformat()
                            fixture_data['datetime_obj'] = parsed_date
                    except: pass
            fixture_data['is_live'] = table.find('img', src=lambda x: x and 'live.gif' in x) is not None
            return fixture_data
        except: return None

    def get_fixtures_for_sport(self, sport_url):
        try:
            response = self.session.get(sport_url, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')
            today_day = datetime.now().day
            tables = soup.find_all('table', {'cellpadding': '1', 'cellspacing': '2'})
            fixtures = []
            for t in tables:
                f = self._parse_broadcast_item(t)
                if f:
                    dt = f.get('datetime_obj')
                    if (dt and dt.day == today_day) or (str(today_day) in f.get('date_time', '')):
                        fixtures.append(f)
            return fixtures
        except: return []

    def get_event_details_concurrent(self, event_url):
        try:
            resp = self.session.get(event_url, timeout=10)
            soup = BeautifulSoup(resp.content, 'html.parser')
            details = {'streams': []}
            lb = soup.find('div', id='links_block')
            if lb:
                for t in lb.find_all('table', class_='lnktbj'):
                    cells = t.find_all('td')
                    if len(cells) >= 7 and cells[5].find('a'):
                        details['streams'].append({
                            'language': cells[0].find('img').get('title', 'Multi') if cells[0].find('img') else 'Multi',
                            'stream_url': urljoin(self.base_url, cells[5].find('a').get('href')),
                            'stream_type': cells[6].get_text(strip=True)
                        })
            return details
        except: return None

    def process_fixture_concurrent(self, fixture):
        url = fixture.get('event_url')
        if url:
            d = self.get_event_details_concurrent(url)
            if d: fixture.update(d)
        return fixture

# CRITICAL FIX: Ensure max_workers has a default value for safe importing
def run_scraper_and_get_data(max_workers=15):
    scraper = BroadcastScraper(max_workers=max_workers)
    sport_url = "https://livetv.sx/enx/allupcomingsports/1/"
    today_fixtures = scraper.get_fixtures_for_sport(sport_url)
    final_data_map = {}
    with ThreadPoolExecutor(max_workers=scraper.max_workers) as executor:
        futures = {executor.submit(scraper.process_fixture_concurrent, f): f for f in today_fixtures}
        for future in as_completed(futures):
            try:
                item = future.result(timeout=45)
                if not item: continue
                eid = item.get('event_id') or str(uuid.uuid4())
                if 'datetime_obj' in item: del item['datetime_obj']
                final_data_map[eid] = {
                    "matchup": item.get("matchup", "Unknown"),
                    "event_url": item.get("event_url", ""),
                    "competition": item.get("competition", "General"),
                    "parsed_datetime": item.get("parsed_datetime", ""),
                    "is_live": item.get("is_live", False),
                    "streams": item.get("streams", []),
                    "last_updated": datetime.now().isoformat()
                }
            except Exception as e:
                print(f"Skipping thread: {e}")
    return final_data_map

if __name__ == "__main__":
    run_scraper_and_get_data()
