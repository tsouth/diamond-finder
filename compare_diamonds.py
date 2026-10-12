"""Merge retailer exports, rank by target dimensions, and flag potential duplicates.
Run: py compare_diamonds.py
"""
import argparse
import math
from pathlib import Path

from criteria import dimension_score, dutch_shortlist_candidate, numeric, quality_status, shape_status
from identity import assign_match_groups, extract_report, extract_supplier_id
from storage import CURRENT, REPORTS, read_csv, write_csv

COLUMNS = [
    'rank', 'retailer', 'inventory_id', 'carat', 'shape', 'color', 'clarity',
    'length_mm', 'width_mm', 'ratio', 'depth_pct', 'table_pct', 'polish', 'symmetry',
    'price_usd', 'certificate', 'supplier_stock_id', 'dimension_score', 'quality_status',
    'shape_status', 'duplicate_group', 'product_url', 'image_url', 'video_url', 'title',
]


def clean(v):
    return str(v or '').strip()


def normalize(source, r):
    if source == 'Stienhardt':
        out = dict(
            retailer=source, inventory_id=r.get('sku'), carat=r.get('carat'), shape='Dutch Marquise',
            color=r.get('color'), clarity=r.get('clarity'), length_mm=r.get('length_mm'),
            width_mm=r.get('width_mm'), ratio=r.get('ratio'), depth_pct=r.get('depth_pct'),
            table_pct=r.get('table_pct'), polish=r.get('polish'), symmetry=r.get('symmetry'),
            price_usd=r.get('price_usd'), certificate=r.get('certificate'),
            supplier_stock_id='', product_url=r.get('product_url'),
            image_url=r.get('image_url'), video_url=r.get('video_360_url'), title=r.get('sku'),
        )
    elif source == 'Aurelinne':
        out = dict(
            retailer=source, inventory_id=r.get('id'), carat=r.get('carat'), shape=r.get('shape'),
            color=r.get('color'), clarity=r.get('clarity'), length_mm=r.get('length_mm'),
            width_mm=r.get('width_mm'), ratio=r.get('lw_ratio'), depth_pct=r.get('depth_pct'),
            table_pct=r.get('table_pct'), polish=r.get('polish'), symmetry=r.get('symmetry'),
            price_usd=r.get('price'),
            certificate=extract_report(r.get('certificate_number'), r.get('certificate')),
            supplier_stock_id=extract_supplier_id(r.get('supplier_stock_id')),
            product_url=('https://aurelinne.com/pages/lab-grown?id=' + str(r.get('id')) + '&stoneType=diamond') if r.get('id') else '',
            image_url=r.get('image_url'), video_url=r.get('video_url'), title=r.get('title'),
        )
    elif source in ('Loose Grown Diamond', 'Mikado Diamonds'):
        out = dict(
            retailer=source, inventory_id=r.get('id'), carat=r.get('carat'), shape=r.get('shape'),
            color=r.get('color'), clarity=r.get('clarity'), length_mm=r.get('length_mm'),
            width_mm=r.get('width_mm'), ratio=r.get('ratio'), depth_pct=r.get('depth_pct'),
            table_pct=r.get('table_pct'), polish=r.get('polish'), symmetry=r.get('symmetry'),
            price_usd=r.get('price_usd'),
            certificate=extract_report(r.get('certificate'), r.get('title')),
            supplier_stock_id=extract_supplier_id(r.get('supplier_stock_id'), r.get('sku'), r.get('title'), r.get('id')),
            product_url=r.get('url'), image_url=r.get('image_url'), video_url=r.get('video_url'), title=r.get('title'),
        )
    else:
        out = dict(
            retailer=source, inventory_id=r.get('id'), carat=r.get('carat'),
            shape=r.get('shape') or ('Square Radiant' if 'square radiant' in r.get('title', '').lower() else 'Other (unverified)'),
            color=r.get('color'), clarity=r.get('clarity'), length_mm='', width_mm='', ratio='',
            depth_pct='', table_pct='', polish='', symmetry='', price_usd=r.get('price_usd'),
            certificate=extract_report(r.get('certificate')), supplier_stock_id='',
            product_url=r.get('url'), image_url='', video_url='', title=r.get('title'),
        )
    if 'HEXAGONAL MODIFIED STEP CUT' in clean(r.get('shape_verified')).upper():
        out['shape'] = 'EXCLUDED - Hexagonal Modified Step Cut'
    return {k: clean(v) for k, v in out.items()}


def rank(rows):
    for r in rows:
        length, width = numeric(r['length_mm']), numeric(r['width_mm'])
        ratio = numeric(r['ratio']) or (length / width if length and width else None)
        r['ratio'] = f'{ratio:.3f}' if ratio else ''
        r['dimension_score'] = dimension_score(length, width)
        r['shape_status'] = shape_status(r)
        r['quality_status'] = quality_status(r)
        r['certificate'] = extract_report(r.get('certificate')) or r.get('certificate', '')
        r['supplier_stock_id'] = extract_supplier_id(r.get('supplier_stock_id')) or r.get('supplier_stock_id', '')
    assign_match_groups(rows)
    rows.sort(key=lambda r: (
        0 if r['quality_status'].startswith('PASS') else 1 if r['quality_status'].startswith('UNKNOWN') else 2,
        0 if r['retailer'] == 'Stienhardt' else 1,
        numeric(r['dimension_score']) if numeric(r['dimension_score']) is not None else math.inf,
        numeric(r['price_usd']) if numeric(r['price_usd']) is not None else math.inf,
    ))
    for i, r in enumerate(rows, 1):
        r['rank'] = i
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--folder', default=str(CURRENT), help='Directory with retailer CSV exports')
    ap.add_argument('--output', default=str(REPORTS / 'master_diamond_comparison.csv'))
    args = ap.parse_args()
    folder = Path(args.folder)
    files = [
        ('Stienhardt', 'diamonds_enriched.csv'),
        ('Aurelinne', 'aurelinne_diamonds.csv'),
        ('Calavera', 'calavera_diamonds.csv'),
        ('Mikado Diamonds', 'mikado_diamonds.csv'),
    ]
    rows = []
    for source, filename in files:
        source_path = folder / filename
        records = read_csv(source_path)
        if not source_path.exists(): print(f'MISSING: {source_path} (skipping)')
        print(f'{source}: {len(records)} rows')
        rows.extend(normalize(source, r) for r in records)
    unique = {}
    for r in rows:
        key = (r['retailer'], r['inventory_id'] or r['product_url'] or r['title'])
        unique[key] = r
    detail_path = folder / 'calavera_other_details.csv'
    details = {r['id']: r for r in read_csv(detail_path) if r.get('id')} if detail_path.exists() else {}
    for r in unique.values():
        if r['retailer'] == 'Calavera' and r['inventory_id'] in details:
            d = details[r['inventory_id']]
            for source_key, dest_key in [
                ('length_mm', 'length_mm'), ('width_mm', 'width_mm'), ('ratio', 'ratio'),
                ('depth_pct', 'depth_pct'), ('table_pct', 'table_pct'), ('polish', 'polish'),
                ('symmetry', 'symmetry'), ('certificate', 'certificate'),
            ]:
                if d.get(source_key):
                    r[dest_key] = d[source_key]
            if d.get('detail_cut') == 'HEXAGONAL MODIFIED STEP CUT':
                r['shape'] = 'EXCLUDED - Hexagonal Modified Step Cut'
    rows = rank(list(unique.values()))
    output = Path(args.output)
    write_csv(output, rows, COLUMNS)
    print(f'Wrote {len(rows)} records to {output}; {sum(r["quality_status"].startswith("PASS") for r in rows)} pass numerical filters.')
    print('WARNING: Unverified OTHER/hexagonal shapes require photo/report confirmation. Dedup by report number or supplier stock id.')
    shortlist = [r for r in rows if dutch_shortlist_candidate(r)]
    write_csv(REPORTS / 'dutch_marquise_review.csv', shortlist, COLUMNS)
    print(f'Wrote {len(shortlist)} labeled-Dutch or unverified OTHER candidates to dutch_marquise_review.csv (not all confirmed Dutch).')


if __name__ == '__main__':
    main()
