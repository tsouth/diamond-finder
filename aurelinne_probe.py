"""Aurelinne feed collector. Browser-matched payload; no cookies required.

py aurelinne_probe.py --pages 2 --browser-test
py aurelinne_probe.py --pages 20
py aurelinne_probe.py --pages 20 --target
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

import requests
from aurelinne_import import FIELDS, extract, parse
from storage import CURRENT, RAW, ensure_layout

URL = 'https://aurelinne.com/apps/diamond-proxy/api/v2/feed'
BATCH = 20
REFERER = ('https://aurelinne.com/pages/lab-grown?activeTab=Lab+Grown&queryLabGrown=true'
           '&carats_min=3.5&carats_max=4.5&color_min=E&color_max=D'
           '&clarity_min=VS1&clarity_max=FL&cut_min=EX&cut_max=EX'
           '&table_percentage_min=55&table_percentage_max=65'
           '&ratio_min=1.75&ratio_max=1.9&polish=EX')


def payload_for(offset, target=False):
    # Exact spellings and values captured from a working Chrome POST request.
    query = {
        'labgrown': True,
        'shapes': ['ROUND','OVAL','EMERALD','PEAR','PRINCESS','CUSHION BRILLIANT',
                   'CUSHION MODIFIED','CUSHION','RADIANT','MARQUISE','HEART',
                   'SQUARE EMERALD','ASSCHER','SQUARE RADIANT','OLD MINER',
                   'EUROPEAN CUT','BAGUETTE','OTHER'],
        'certificate_lab': ['GIA','IGI','HRD','WISE'],
        'color': ['E','D'],
        'sizes': {'from': 3.5, 'to': 4.5},
        'clarity': ['VS1','VVS2','VVS1','IF','FL'],
        'cut': ['EX'], 'polish': ['EX'],
        'symmetry': ['GD','VG','EX'],
        'flouresence': ['NON','FNT','MED','STG','VST'],
        'labgrown_type': [],
        'ratio': {'from': '1.75', 'to': '1.9'},
        'table_percentage': {'from': 55, 'to': 65},
    }
    if target:
        query['shapes'] = ['OTHER']  # regular MARQUISE confirmed not Dutch; OTHER still needs visual inspection
        query['sizes'] = {'from': 3.0, 'to': 5.2}
        query['ratio'] = {'from': '1.80', 'to': '2.12'}
        # No additional API-level restrictions: rank locally to avoid missing inventory.
    return {'showTarrifFreeFeeds': False, 'callFrom': 'feed',
            'query': query, 'offset': offset,
            'order': {'type': 'price', 'direction': 'ASC'}}


def collect(session, pages, delay, target, start_offset):
    seen = {}
    for page in range(pages):
        offset = start_offset + page * BATCH
        response = session.post(URL, json=payload_for(offset, target), timeout=40)
        print(f'offset={offset}: HTTP {response.status_code}; type={response.headers.get("Content-Type", "unknown")}', flush=True)
        if not response.ok:
            print('Response preview:', response.text[:900])
            response.raise_for_status()
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(f'Non-JSON response: {response.text[:900]!r}') from exc
        if page == 0:
            print('Response structure:', f'list length {len(body)}' if isinstance(body,list) else f'object keys {list(body)}' if isinstance(body,dict) else type(body).__name__)
            if not body:
                print('Empty result: browser-matched request returned no diamonds. Compare headers/session or filters.')
        try:
            records = extract(body)
        except ValueError as exc:
            raise RuntimeError(f'Unexpected response: {str(body)[:900]}') from exc
        if not records:
            print('Empty batch; stopping.')
            break
        new = 0
        for item in records:
            if isinstance(item,dict) and item.get('id') and item['id'] not in seen:
                seen[item['id']] = item
                new += 1
        print(f'  received={len(records)} new={new} unique_total={len(seen)}')
        if not new or len(records) < BATCH:
            print('Pagination finished (no new records or short batch).')
            break
        if page < pages - 1:
            time.sleep(delay)
    else:
        print('Reached page limit; inventory may continue.')
    return list(seen.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pages', type=int, default=20)
    ap.add_argument('--delay', type=float, default=0.6)
    ap.add_argument('--target', action='store_true', help='Apply target carat/ratio and OTHER/MARQUISE shape API filters')
    ap.add_argument('--browser-test', action='store_true', help='Test the exact captured browser payload at offset 140 (default one request)')
    ap.add_argument('--start-offset', type=int, default=0)
    ap.add_argument('--output', default=str(CURRENT/'aurelinne_diamonds.csv'))
    ap.add_argument('--json-output', default=str(RAW/'aurelinne'/'all_results.json'))
    args = ap.parse_args()
    if args.pages < 1 or args.delay < 0 or args.start_offset < 0 or args.start_offset % BATCH:
        ap.error('--pages >= 1; --delay >= 0; --start-offset must be a nonnegative multiple of 20')
    ensure_layout();Path(args.json_output).parent.mkdir(parents=True,exist_ok=True)
    start_offset = 140 if args.browser_test else args.start_offset
    pages = 1 if args.browser_test else args.pages
    session = requests.Session()
    session.headers.update({
        'Accept': '*/*', 'Content-Type': 'application/json',
        'Origin': 'https://aurelinne.com', 'Referer': REFERER,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    try:
        records = collect(session, pages, args.delay, args.target, start_offset)
    except (requests.RequestException, RuntimeError) as exc:
        print(f'Request failed: {exc}', file=sys.stderr)
        return 1
    Path(args.json_output).write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    rows = parse(records)
    with open(args.output, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f'Wrote {len(rows)} diamonds to {args.output}; {sum(r["match_target"].startswith("YES") for r in rows)} pass numerical filters.')
    print('OTHER or MARQUISE does not confirm Dutch marquise; inspect photos and reports.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
