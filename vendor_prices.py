"""Exact-certificate price checks across the configured retailer universe."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote_plus
from urllib.parse import urljoin, urlparse

import requests

from identity import extract_report
from pricing import money
from storage import CONFIG, REPORTS, read_json, write_csv, write_json


@dataclass(frozen=True)
class Vendor:
    name: str
    domain: str
    search_url: str


VENDORS = (
    Vendor('Aurelinne', 'aurelinne.com', 'https://aurelinne.com/search?q={report}'),
    Vendor('Mikado Diamonds', 'mikadodiamonds.com', 'https://mikadodiamonds.com/search?q={report}&type=product'),
    Vendor('Stienhardt', 'stienhardt.com', 'https://stienhardt.com/search?q={report}'),
    Vendor('Calavera', 'calaveranewyork.com', 'https://calaveranewyork.com/search?q={report}&type=product'),
    Vendor('Ritani', 'ritani.com', 'https://www.ritani.com/search?q={report}'),
    Vendor('Rare Carat', 'rarecarat.com', 'https://www.rarecarat.com/search?q={report}'),
    Vendor('Loose Grown Diamond', 'loosegrowndiamond.com', 'https://www.loosegrowndiamond.com/lab-diamonds/?sku={digits}'),
    Vendor('Adiamor', 'adiamor.com', 'https://adiamor.com/diamonds/search/lab-grown?search={digits}'),
    Vendor('Brilliance', 'brilliance.com', 'https://www.brilliance.com/search?q={report}'),
    Vendor('With Clarity', 'withclarity.com', 'https://www.withclarity.com/search?q={report}'),
    Vendor('Friendly Diamonds', 'friendlydiamonds.com', 'https://friendlydiamonds.com/search?q={report}'),
)


def _price_from_html(text: str) -> float | None:
    patterns = (
        r'<meta[^>]+(?:property|name)=["\'](?:product:price:amount|og:price:amount)["\'][^>]+content=["\']([\d,.]+)',
        r'["\']price["\']\s*:\s*["\']?([\d,.]+)',
        r'\$\s*([1-9][\d,]*(?:\.\d{2})?)',
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            value = money(match.group(1))
            if value is not None and value >= 100: return float(value)
    return None


def inspect_response(report: str, response, url: str) -> dict:
    checked = datetime.now(timezone.utc).isoformat()
    base = {'certificate': report, 'checked_at': checked, 'query_url': url,
            'http_status': getattr(response, 'status_code', ''), 'currency': 'USD'}
    if getattr(response, 'status_code', 0) in (401, 403, 429):
        return {**base, 'status': 'blocked', 'price': '', 'product_url': '', 'notes': 'HTTP access blocked or rate limited'}
    if not getattr(response, 'ok', False):
        return {**base, 'status': 'error', 'price': '', 'product_url': '', 'notes': f'HTTP {base["http_status"]}'}
    text = response.text
    digits = re.sub(r'\D', '', report)
    if report.upper() not in text.upper() and digits not in text:
        js_only = len(re.sub(r'<[^>]+>', ' ', text).strip()) < 300
        return {**base, 'status': 'unresolved' if js_only else 'not_found', 'price': '',
                'product_url': '', 'notes': 'Certificate absent from returned page' + ('; client-side rendering likely' if js_only else '')}
    price = _price_from_html(text)
    return {**base, 'status': 'priced' if price is not None else 'found_no_price',
            'price': f'{price:.2f}' if price is not None else '', 'product_url': getattr(response, 'url', url),
            'notes': 'Exact certificate present in response'}


def product_links(text: str, source_url: str, report: str) -> list[str]:
    """Return product-looking links whose anchor/card contains the exact report."""
    links = []
    digits = re.sub(r'\D', '', report)
    for match in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', text, re.I | re.S):
        href, body = match.groups()
        if report.upper() not in body.upper() and digits not in body:
            continue
        absolute = urljoin(source_url, href)
        path = urlparse(absolute).path.lower()
        if '/search' not in path and absolute not in links:
            links.append(absolute)
    return links


def _known(listings: list[dict]) -> dict[tuple[str, str], dict]:
    result = {}
    for row in listings:
        report = extract_report(row.get('certificate'))
        if report and row.get('retailer'):
            result[(report, row['retailer'])] = row
    return result


def check_one(vendor: Vendor, report: str, known: dict, live: bool) -> dict:
    observed = known.get((report, vendor.name))
    url = (observed or {}).get('product_url') or vendor.search_url.format(report=quote_plus(report), digits=re.sub(r'\D', '', report))
    if not live:
        if observed:
            price = money(observed.get('price_usd'))
            return {'certificate': report, 'retailer': vendor.name, 'status': 'recorded_snapshot',
                    'price': f'{price:.2f}' if price is not None else '', 'currency': observed.get('currency','USD'),
                    'availability': observed.get('availability','historical snapshot'), 'checked_at': '',
                    'query_url': url, 'product_url': observed.get('product_url',''), 'http_status': '',
                    'notes': observed.get('verification','Saved offer; live check skipped in offline mode'), 'known_listing': True}
        return {'certificate': report, 'retailer': vendor.name, 'status': 'offline_not_checked',
                'price': '', 'currency': 'USD', 'availability': '', 'checked_at': '', 'query_url': url,
                'product_url': '', 'http_status': '', 'notes': 'Run without --offline for an active lookup', 'known_listing': False}
    try:
        response = requests.get(url, timeout=25, headers={'User-Agent':'Mozilla/5.0 DiamondFinder/17 (+exact certificate price comparison)'})
        if observed:
            result = inspect_response(report, response, url)
            if result['status'] == 'not_found':
                result['status'] = 'known_unresolved'
                result['notes'] = 'Known product page did not expose the certificate in server-rendered HTML'
        elif response.ok:
            links = product_links(response.text, url, report)
            if not links:
                result = {'certificate': report, 'checked_at': datetime.now(timezone.utc).isoformat(),
                          'query_url': url, 'http_status': response.status_code, 'currency': 'USD',
                          'status': 'not_found', 'price': '', 'product_url': '',
                          'notes': 'No certificate-linked product result returned'}
            else:
                product = requests.get(links[0], timeout=25, headers={'User-Agent':'Mozilla/5.0 DiamondFinder/17'})
                result = inspect_response(report, product, links[0])
        else:
            result = inspect_response(report, response, url)
    except requests.RequestException as exc:
        result = {'certificate': report, 'checked_at': datetime.now(timezone.utc).isoformat(),
                  'query_url': url, 'http_status': '', 'currency': 'USD', 'status': 'error',
                  'price': '', 'product_url': '', 'notes': type(exc).__name__}
    result['retailer'] = vendor.name
    result['known_listing'] = bool(observed)
    result['availability'] = 'listed' if result['status'] == 'priced' else ''
    return result


def run(reports: list[str], listings: list[dict], live: bool = True, workers: int = 6) -> list[dict]:
    known = _known(listings)
    jobs = [(vendor, report) for report in reports for vendor in VENDORS]
    if not live:
        return [check_one(vendor, report, known, False) for vendor, report in jobs]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(check_one, vendor, report, known, True) for vendor, report in jobs]
        return [future.result() for future in futures]


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--offline', action='store_true'); parser.add_argument('--workers', type=int, default=6); args = parser.parse_args()
    listings = read_json(CONFIG / 'confirmed_listings.json')
    reports = list(dict.fromkeys(extract_report(row.get('certificate')) for row in listings if extract_report(row.get('certificate'))))
    rows = run(reports, listings, live=not args.offline, workers=args.workers)
    write_csv(REPORTS / 'vendor_price_checks.csv', rows)
    write_json(REPORTS / 'vendor_price_checks.json', rows)
    counts = {status: sum(row['status'] == status for row in rows) for status in sorted({row['status'] for row in rows})}
    print(f'Checked {len(reports)} certificates across {len(VENDORS)} retailers: {json.dumps(counts, sort_keys=True)}')


if __name__ == '__main__': main()
