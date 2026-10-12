"""Cross-retailer comparison by IGI report or supplier stock id, with transparent promo math.

py cross_retailer_prices.py
py cross_retailer_prices.py --input master_diamond_comparison.csv

Input can be an existing master CSV or the included inventory snapshot.
Overrides in confirmed_listings.json are user-confirmed observations, not live stock.
"""
import argparse
from collections import defaultdict
from datetime import date

from criteria import facet_verification
from identity import assign_match_groups, extract_report, extract_supplier_id
from pricing import FALL10, apply_promo, numeric_price as num
from storage import CONFIG, REFERENCE, REPORTS, read_csv, read_json, write_csv

PROMO = FALL10


def listing_matches_override(row, override) -> bool:
    if str(row.get('retailer') or '').casefold() != str(override.get('retailer') or '').casefold():
        return False
    if override.get('inventory_id') and str(row.get('inventory_id') or '') == str(override['inventory_id']):
        return True
    report = extract_report(override.get('certificate'))
    if report and extract_report(row.get('certificate')) == report:
        return True
    stock = extract_supplier_id(override.get('supplier_stock_id'))
    return bool(stock and extract_supplier_id(row.get('supplier_stock_id')) == stock)


def apply_overrides(rows, overrides):
    for override in overrides:
        target = next((r for r in rows if listing_matches_override(r, override)), None)
        if target is None:
            target = {k: '' for k in rows[0]} if rows else {}
            rows.append(target)
        for k, v in override.items():
            if k != 'verification':
                target[k] = v
        target['source_note'] = override.get('verification', '')
        if override.get('certificate'):
            target['certificate'] = extract_report(override.get('certificate')) or override['certificate']
        if override.get('supplier_stock_id'):
            target['supplier_stock_id'] = extract_supplier_id(override.get('supplier_stock_id')) or override['supplier_stock_id']
    return rows


def enrich_prices(rows, as_of):
    assign_match_groups(rows)
    for row in rows:
        row.update(apply_promo(row.get('price_usd'), row.get('retailer'), as_of, PROMO))
        row['source_note'] = row.get('source_note', '')
        row['shape_verification'] = facet_verification(row)
        row.setdefault('supplier_stock_id', '')
    return rows


def same_stone_comparisons(rows):
    groups = defaultdict(list)
    for row in rows:
        key = row.get('duplicate_group') or row.get('normalized_report')
        if key:
            groups[key].append(row)
    comparisons = []
    for key, items in groups.items():
        retailers = {i.get('retailer') for i in items}
        if len(retailers) < 2:
            continue
        priced = [i for i in items if num(i.get('effective_price_usd')) is not None]
        if not priced:
            continue
        priced.sort(key=lambda r: num(r['effective_price_usd']))
        lowest = priced[0]['effective_price_usd']
        report = next((i.get('normalized_report') for i in priced if i.get('normalized_report')), key)
        for row in priced:
            comparisons.append({
                'report': report,
                'match_key': key,
                'retailer': row.get('retailer', ''),
                'inventory_id': row.get('inventory_id', ''),
                'listed_price_usd': row.get('price_usd', ''),
                'promo_code': row.get('promo_code', ''),
                'promo_status': row.get('promo_status', ''),
                'effective_price_usd': row.get('effective_price_usd', ''),
                'lowest_price_usd': lowest,
                'savings_vs_lowest_usd': f"{num(row['effective_price_usd']) - num(lowest):.2f}",
                'product_url': row.get('product_url', ''),
                'source_note': row.get('source_note', ''),
            })
    return comparisons


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='master_diamond_comparison.csv')
    parser.add_argument('--date', default=date.today().isoformat())
    args = parser.parse_args()
    source = REPORTS / args.input
    if not source.exists() and args.input == 'master_diamond_comparison.csv':
        source = REFERENCE / 'inventory_snapshot.csv'
    if not source.exists():
        raise SystemExit('Input CSV not found: ' + str(source))
    rows = read_csv(source)
    overrides = read_json(CONFIG / 'confirmed_listings.json')
    apply_overrides(rows, overrides)
    enrich_prices(rows, args.date)
    rows.sort(key=lambda r: (num(r['effective_price_usd']) is None, num(r['effective_price_usd']) or float('inf')))
    columns = list(dict.fromkeys(k for r in rows for k in r))
    write_csv(REPORTS / 'diamond_prices_with_promos.csv', rows, columns)
    comparisons = same_stone_comparisons(rows)
    fields = [
        'report', 'match_key', 'retailer', 'inventory_id', 'listed_price_usd', 'promo_code',
        'promo_status', 'effective_price_usd', 'lowest_price_usd', 'savings_vs_lowest_usd',
        'product_url', 'source_note',
    ]
    write_csv(REPORTS / 'same_diamond_price_comparison.csv', comparisons, fields)
    groups = {r['normalized_report'] for r in rows if r.get('normalized_report')}
    print(f'Input: {source.name}; listings: {len(rows)}; unique reports: {len(groups)}; cross-retailer report groups: {len(set(r["report"] for r in comparisons))}')
    as_of = date.fromisoformat(args.date)
    promo_state = 'expired' if as_of > date.fromisoformat(PROMO.end) else PROMO.code
    print('Promotion:', promo_state, '| Valid through', PROMO.end, '| checkout must confirm')
    print('Wrote diamond_prices_with_promos.csv and same_diamond_price_comparison.csv')
    for row in comparisons:
        if row['report'] == 'LG825678759':
            print('LG825678759:', row['retailer'], row['effective_price_usd'], row['promo_status'])


if __name__ == '__main__':
    main()
