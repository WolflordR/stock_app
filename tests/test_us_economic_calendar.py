from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import requests

from apps.api.read_models import list_us_market_calendar
from modules.data_sources.us_economic_calendar import (
    load_official_us_calendar, parse_fomc_calendar, parse_new_york_fed_month,
)


HTML = '''<table class="research-table-1col"><tr><td></td><td>Monday</td></tr>
<tr><td></td><td><div>14<br><span class="ts-accordion-content">
<a href="https://www.bls.gov/cpi/">Consumer Price Index</a><br>(08:30)<br>
<a href="https://www.bls.gov/news.release/ppi.toc.htm">Producer Price Index (PPI)</a><br>(10:00)<br>
</span></div></td></tr></table>'''


class UsEconomicCalendarTests(unittest.TestCase):
    def test_fomc_statement_uses_meeting_end_date_and_taipei_time(self):
        html = '''<div class="panel"><div class="panel-heading"><h4>2026 FOMC Meetings</h4></div>
        <div class="fomc-meeting"><div class="fomc-meeting__month">October</div>
        <div class="fomc-meeting__date">27-28</div></div></div>'''
        rows = parse_fomc_calendar(html, 2026)
        self.assertEqual((rows[0]['date'], rows[0]['time'], rows[0]['importance']),
                         ('2026-10-29', '02:00', 'high'))

    def test_official_release_times_convert_to_taipei_and_filter(self):
        rows = parse_new_york_fed_month(HTML, 2026, 10, 'https://www.newyorkfed.org/research/calendars/i-oct26.html')
        self.assertEqual([(row['event'], row['time']) for row in rows],
                         [('消費者物價指數 CPI', '20:30'), ('生產者物價指數 PPI', '22:00')])
        self.assertTrue(all(row['importance'] == 'high' for row in rows))
        with patch('apps.api.read_models.load_official_us_calendar', return_value={
            'rows': rows, 'source': 'official', 'source_label': 'NY Fed',
            'last_updated_at': '2026-10-08T00:00:00+00:00', 'errors': [],
        }):
            result = list_us_market_calendar(start_date='2026-10-14', end_date='2026-10-14', importance='high')
        self.assertEqual(result['event_count'], 2)
        self.assertEqual(result['time_zone'], 'Asia/Taipei')

    def test_last_successful_schedule_survives_source_failure(self):
        response = requests.Response()
        response.status_code = 200
        response._content = HTML.encode()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'calendar.json'
            with patch('modules.data_sources.us_economic_calendar.requests.get', return_value=response):
                live = load_official_us_calendar(date(2026, 10, 14), date(2026, 10, 14), path=path)
            self.assertEqual(live['source'], 'official')
            cache = json.loads(path.read_text())
            cache['2026-10']['fetched_at'] = '2026-01-01T00:00:00+00:00'
            path.write_text(json.dumps(cache))
            with patch('modules.data_sources.us_economic_calendar.requests.get', side_effect=requests.ConnectionError('offline')):
                stale = load_official_us_calendar(date(2026, 10, 14), date(2026, 10, 14), path=path)
            self.assertEqual(stale['source'], 'official_cache')
            self.assertEqual(len(stale['rows']), 2)


if __name__ == '__main__':
    unittest.main()
