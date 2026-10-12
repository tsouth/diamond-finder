"""Generate an auditable retailer-coverage and exact-identifier search plan."""
from __future__ import annotations

from collections import defaultdict
from urllib.parse import quote_plus

from identity import extract_report, extract_supplier_id
from storage import CONFIG, REPORTS, read_json, write_csv, write_json


def search_terms(row: dict) -> list[str]:
    values = [extract_report(row.get('certificate')),
              extract_supplier_id(row.get('supplier_stock_id'), row.get('sku')),
              row.get('inventory_id')]
    terms = []
    for value in values:
        value = str(value or '').strip()
        if value and value not in terms: terms.append(value)
    if row.get('carat') and row.get('length_mm') and row.get('width_mm'):
        terms.append(f"{row['carat']} E VVS1 {row['length_mm']} {row['width_mm']} diamond")
    return terms


def build(coverage: list[dict], listings: list[dict]) -> tuple[list[dict], dict]:
    offers = defaultdict(list)
    queries = defaultdict(list)
    for listing in listings:
        report = extract_report(listing.get('certificate'))
        if report:
            offers[listing.get('retailer','')].append(report)
            for term in search_terms(listing):
                if term not in queries[report]: queries[report].append(term)
    rows = []
    for item in coverage:
        retailer = item.get('retailer','')
        rows.append({**item, 'matching_certificates': ' | '.join(sorted(set(offers[retailer]))),
                     'matching_offer_count': len(offers[retailer])})
    plan = {
        'disclaimer': 'Coverage is measurable, never guaranteed exhaustive.',
        'retailers_recorded': len(coverage),
        'retailers_checked': sum(bool(row.get('last_checked_at')) for row in coverage),
        'retailers_not_searched': [row.get('retailer') for row in coverage if row.get('status') == 'not searched'],
        'exact_searches': {report: [
            {'term': term, 'web_search_url': f'https://www.google.com/search?q={quote_plus(chr(34)+term+chr(34)+" diamond")}' }
            for term in terms] for report, terms in queries.items()},
    }
    return rows, plan


def main():
    coverage = read_json(CONFIG / 'retailer_coverage.json'); listings = read_json(CONFIG / 'confirmed_listings.json')
    rows, plan = build(coverage, listings)
    write_csv(REPORTS / 'retailer_coverage.csv', rows); write_json(REPORTS / 'exact_search_plan.json', plan)
    print(f"Wrote coverage for {plan['retailers_recorded']} retailers ({plan['retailers_checked']} checked)")


if __name__ == '__main__': main()
