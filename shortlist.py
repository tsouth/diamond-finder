"""Canonical one-row-per-diamond shortlist and associated retailer offers."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date

from confidence import (certificate_summary, index_by_report, offer_freshness,
                        optical_summary, readiness)
from criteria import CLARITIES, COLORS, FINISH_OK, preference_flags, ranking_components
from identity import extract_report, extract_supplier_id
from pricing import apply_promo, money
from storage import CERTIFICATES, CONFIG, REPORTS, read_json, write_csv, write_json

def qualification_status(row: dict) -> str:
    style = str(row.get('shape') or row.get('cutting_style') or '').strip().upper()
    if 'HEXAGONAL MODIFIED STEP CUT' in style:
        return 'REJECT - Hexagonal Modified Step Cut'
    if row.get('cutting_style_status') != 'verified_igi' or style != 'HEXAGONAL MODIFIED BRILLIANT':
        return 'PENDING - verify IGI cutting style'
    if str(row.get('color') or '').upper() not in COLORS:
        return 'REJECT - color outside D/E'
    if str(row.get('clarity') or '').upper() not in CLARITIES:
        return 'REJECT - clarity below VS1'
    if str(row.get('polish') or '').lower() not in FINISH_OK:
        return 'REJECT - polish not Excellent'
    if str(row.get('symmetry') or '').lower() not in FINISH_OK:
        return 'REJECT - symmetry not Excellent'
    if not row.get('length_mm') or not row.get('width_mm'):
        return 'PENDING - missing dimensions'
    return 'CERTIFICATE QUALIFIED - optical review pending'


def _completeness(row: dict) -> int:
    keys = ('carat','color','clarity','length_mm','width_mm','height_mm','ratio','table_pct',
            'depth_pct','polish','symmetry','shape','cutting_style_status','certificate_url')
    return sum(row.get(key) not in ('', None) for key in keys)


def _offer(row: dict, as_of: str) -> dict:
    promo = apply_promo(row.get('price_usd'), row.get('retailer'), as_of)
    offer = {
        'certificate': extract_report(row.get('certificate')),
        'retailer': row.get('retailer',''), 'inventory_id': str(row.get('inventory_id') or ''),
        'supplier_namespace': row.get('supplier_namespace',''),
        'supplier_stock_id': extract_supplier_id(row.get('supplier_stock_id'), row.get('sku')),
        'listed_price': f"{money(row.get('price_usd')):.2f}" if money(row.get('price_usd')) is not None else '',
        'currency': row.get('currency') or 'USD', 'observed_at': row.get('observed_at',''),
        **promo, 'availability': row.get('availability') or 'historical snapshot',
        'first_seen_at': row.get('first_seen_at') or row.get('observed_at',''),
        'last_seen_at': row.get('last_seen_at') or row.get('observed_at',''),
        'last_checked_at': row.get('last_checked_at') or row.get('observed_at',''),
        'checkout_verified_at': row.get('checkout_verified_at',''),
        'checkout_total': row.get('checkout_total',''),
        'product_url': row.get('product_url',''), 'image_url': row.get('image_url',''),
        'video_url': row.get('video_url',''), 'source_note': row.get('verification',''),
    }
    offer.update(offer_freshness(offer, as_of))
    return offer


def build(rows: list[dict], as_of: str, evidence: dict | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    evidence = evidence or {}
    optical_index = index_by_report(evidence.get('optical', []))
    certificate_index = evidence.get('certificates', {})
    policies = {row.get('retailer'): row for row in evidence.get('policies', [])}
    coverage = evidence.get('coverage', [])
    vendor_checks = evidence.get('vendor_checks', [])
    grouped = defaultdict(list)
    for row in rows:
        report = extract_report(row.get('certificate'))
        if report:
            grouped[report].append(dict(row, certificate=report))
    diamonds, offers = [], []
    for report, records in grouped.items():
        canonical = max(records, key=_completeness)
        group_offers = [_offer(row, as_of) for row in records]
        eligible = [offer for offer in group_offers
                    if offer['currency'] == 'USD' and money(offer['effective_price_usd']) is not None
                    and str(offer['availability']).lower() not in {'unavailable','sold','out of stock'}]
        best = min(eligible, key=lambda offer: money(offer['effective_price_usd'])) if eligible else {}
        components = ranking_components({**canonical, 'effective_price_usd': best.get('effective_price_usd','')})
        warnings = preference_flags(canonical)
        optical = optical_summary(optical_index.get(report))
        certificate = certificate_summary(certificate_index.get(report))
        visual = optical['optical_review_status'] if optical_index.get(report) else canonical.get('visual_review_status') or 'missing'
        optical['optical_review_status'] = visual
        if not optical['optical_review_complete']: warnings.append('structured optical review incomplete')
        if certificate['certificate_evidence_status'] != 'validated': warnings.append('retained IGI report not validated')
        if not canonical.get('certificate_url'): warnings.append('missing IGI report link')
        if not any(o.get('video_url') for o in group_offers): warnings.append('missing stone-specific 360 video')
        diamond = {
            'computed_rank': '', 'provisional_rank': canonical.get('provisional_rank',''),
            'certificate': report, 'carat': canonical.get('carat',''), 'color': canonical.get('color',''),
            'clarity': canonical.get('clarity',''), 'length_mm': canonical.get('length_mm',''),
            'width_mm': canonical.get('width_mm',''), 'height_mm': canonical.get('height_mm',''),
            'ratio': canonical.get('ratio',''), 'table_pct': canonical.get('table_pct',''),
            'depth_pct': canonical.get('depth_pct',''), 'polish': canonical.get('polish',''),
            'symmetry': canonical.get('symmetry',''), 'cutting_style': canonical.get('shape',''),
            'cutting_style_status': canonical.get('cutting_style_status','unverified'),
            'qualification_status': qualification_status(canonical),
            'visual_review_status': visual, 'certificate_url': canonical.get('certificate_url',''),
            **optical, **certificate,
            'dimension_fit_score': components['dimension_fit'],
            'dimension_penalty': components.get('dimension_penalty'),
            'preference_penalty': components['preference_penalty'],
            'evidence_penalty': components['evidence_penalty'],
            'value_component': components['value_component'], 'overall_score': components['overall'],
            'value_score': components.get('value_score'),
            'score_explanation': 'Diamond score (0-100, higher is better) uses dimensional fit, soft preferences, and evidence completeness; price is shown separately in the value score and cheapest-offer fields. Neither is an optical grade.',
            'warnings': '; '.join(warnings), 'offer_count': len(group_offers),
            'cheapest_retailer': best.get('retailer',''), 'cheapest_listed_price': best.get('listed_price',''),
            'cheapest_effective_price': best.get('effective_price_usd',''),
            'cheapest_promo_code': best.get('promo_code',''), 'cheapest_promo_status': best.get('promo_status',''),
            'other_retailers': ' | '.join(sorted(o['retailer'] for o in group_offers if o is not best)),
        }
        offer_retailers = {o.get('retailer') for o in group_offers}
        def check_result(item):
            recorded = (item.get('certificate_checks') or {}).get(report)
            if recorded: return recorded
            if item.get('retailer') in offer_retailers:
                return 'found_archived' if item.get('status') in {'excluded', 'archived'} else 'found'
            return 'not_searched'
        checks = [(item, check_result(item)) for item in coverage]
        active_retailers = {item.get('retailer') for item, result in checks if result == 'found'}
        active_offers = [o for o in group_offers if o.get('retailer') in active_retailers]
        report_checks = [row for row in vendor_checks if extract_report(row.get('certificate')) == report]
        diamond.update({
            'retailer_universe': len(coverage),
            'exact_certificate_searched': sum(result != 'not_searched' for _, result in checks),
            'matching_active_offers': len(active_offers),
            'matching_archived_sources': sum(result == 'found_archived' for _, result in checks),
            'searched_no_match': sum(result == 'not_found' for _, result in checks),
            'fresh_price_observations': sum(o.get('freshness_status') == 'fresh' and money(o.get('listed_price')) is not None for o in active_offers),
            'live_availability_confirmed': sum(bool(o.get('eligible_live_offer')) for o in active_offers),
            'checkout_verified_offers': sum(bool(o.get('checkout_verified_at')) for o in active_offers),
            'coverage_not_searched': ' | '.join(item.get('retailer','') for item, result in checks if result == 'not_searched'),
            'vendor_price_checks': report_checks,
        })
        if report_checks:
            attempted = [row for row in report_checks if row.get('status') != 'offline_not_checked']
            priced = [row for row in report_checks if row.get('status') == 'priced']
            diamond.update({
                'retailer_universe': len(report_checks),
                'exact_certificate_searched': len(attempted),
                'matching_active_offers': sum(row.get('status') == 'priced' or str(row.get('known_listing')).lower() == 'true' for row in report_checks),
                'fresh_price_observations': len(priced),
                'live_availability_confirmed': len(priced),
                'searched_no_match': sum(row.get('status') == 'not_found' for row in report_checks),
                'lookup_blocked_or_error': sum(row.get('status') in {'blocked','error','unresolved'} for row in report_checks),
                'coverage_not_searched': ' | '.join(row.get('retailer','') for row in report_checks if row.get('status') == 'offline_not_checked'),
            })
        status, blockers = readiness(diamond, group_offers, policies.get(best.get('retailer')))
        diamond['purchase_readiness'] = status
        diamond['readiness_blockers'] = '; '.join(blockers)
        diamonds.append(diamond); offers.extend(group_offers)
    diamonds.sort(key=lambda row: (
        not row['qualification_status'].startswith('CERTIFICATE QUALIFIED'),
        row['overall_score'] is None,
        -(row['overall_score'] if row['overall_score'] is not None else float('-inf')),
    ))
    for rank, row in enumerate(diamonds, 1): row['computed_rank'] = rank
    offers.sort(key=lambda row: (row['certificate'], money(row['effective_price_usd']) or money('999999999')))
    nested = []
    for diamond in diamonds:
        nested.append({**diamond, 'offers': [o for o in offers if o['certificate'] == diamond['certificate']]})
    return diamonds, offers, nested


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='confirmed_listings.json')
    parser.add_argument('--date', default=date.today().isoformat())
    args = parser.parse_args()
    rows = read_json(CONFIG / args.input)
    vendor_checks_path = REPORTS / 'vendor_price_checks.json'
    vendor_checks = read_json(vendor_checks_path) if vendor_checks_path.exists() else []
    latest = {(extract_report(item.get('certificate')), item.get('retailer')): item
              for item in vendor_checks if item.get('status') == 'priced'}
    existing, updated_rows = set(), []
    for row in rows:
        key = (extract_report(row.get('certificate')), row.get('retailer'))
        existing.add(key); check = latest.get(key)
        updates = {'price_usd': check['price'], 'observed_at': check['checked_at'][:10],
                   'last_checked_at': check['checked_at'][:10], 'availability': 'available'} if check else {}
        updated_rows.append({**row, **updates})
    for key, check in latest.items():
        if key not in existing:
            updated_rows.append({'certificate':key[0], 'retailer':key[1], 'price_usd':check['price'],
                                 'currency':check.get('currency','USD'), 'observed_at':check['checked_at'][:10],
                                 'last_checked_at':check['checked_at'][:10], 'availability':'available',
                                 'product_url':check.get('product_url') or check.get('query_url',''),
                                 'verification':'Exact-certificate live vendor lookup'})
    rows = updated_rows
    certificates = {}
    if CERTIFICATES.exists():
        for path in CERTIFICATES.glob('LG*.json'):
            item = read_json(path); certificates[extract_report(item.get('certificate'))] = item
    evidence = {
        'certificates': certificates,
        'optical': read_json(CONFIG / 'optical_reviews.json'),
        'policies': read_json(CONFIG / 'vendor_policies.json'),
        'coverage': read_json(CONFIG / 'retailer_coverage.json'),
        'vendor_checks': vendor_checks,
    }
    diamonds, offers, nested = build(rows, args.date, evidence)
    write_csv(REPORTS / 'ranked_shortlist.csv', diamonds)
    write_csv(REPORTS / 'shortlist_offers.csv', offers)
    write_json(REPORTS / 'dashboard_data.json', nested)
    print(f'Wrote {len(diamonds)} unique diamonds, {len(offers)} offers, and dashboard_data.json')


if __name__ == '__main__': main()
