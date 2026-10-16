import json
from pathlib import Path

from provenance import snapshot
from shortlist import build, qualification_status
from storage import CONFIG


ROOT = Path(__file__).resolve().parents[1]


def seeded_rows():
    return json.loads((CONFIG / 'confirmed_listings.json').read_text(encoding='utf-8'))


def test_shortlist_contains_only_current_premium_fl_diamonds():
    diamonds, offers, nested = build(seeded_rows(), '2026-10-12')
    assert len(diamonds) == 5
    assert len(offers) == 5
    assert len(nested) == 5
    assert all(row['clarity'] == 'FL' and 4 <= row['carat'] <= 5 for row in diamonds)


def test_computed_ranking_contains_the_current_fl_search():
    diamonds, _, _ = build(seeded_rows(), '2026-10-12')
    certificates = [row['certificate'] for row in diamonds]
    assert set(certificates) == {
        'LG831628616', 'LG823695685', 'LG824601394', 'LG824601396', 'LG838622718'
    }


def test_shared_diamond_keeps_both_offers_and_cheapest():
    diamonds, offers, _ = build(seeded_rows(), '2026-10-12')
    diamond = next(row for row in diamonds if row['certificate'] == 'LG831628616')
    shared = [row for row in offers if row['certificate'] == 'LG831628616']
    assert {row['retailer'] for row in shared} == {'Mikado Diamonds'}
    assert diamond['offer_count'] == 1
    assert diamond['cheapest_retailer'] == 'Mikado Diamonds'
    assert diamond['cheapest_effective_price'] == '18930.00'


def test_exact_certificate_coverage_is_not_reported_as_live_price_coverage():
    evidence = {
        'coverage': json.loads((CONFIG / 'retailer_coverage.json').read_text(encoding='utf-8')),
        'optical': [], 'policies': [], 'certificates': {},
    }
    diamonds, _, _ = build(seeded_rows(), '2026-10-12', evidence)
    diamond = next(row for row in diamonds if row['certificate'] == 'LG831628616')
    assert diamond['exact_certificate_searched'] == 1
    assert diamond['retailer_universe'] == 11
    assert diamond['matching_active_offers'] == 1
    assert diamond['checkout_verified_offers'] == 0
    assert 'Mikado Diamonds' not in diamond['coverage_not_searched']


def test_verified_step_cut_is_rejected():
    row = dict(seeded_rows()[0], shape='Hexagonal Modified Step Cut')
    assert qualification_status(row).startswith('REJECT')


def test_snapshot_is_immutable_and_hashed(tmp_path):
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config' / 'confirmed_listings.json').write_text('[]', encoding='utf-8')
    target = snapshot(tmp_path, 'run1', 'before')
    manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['files'][0]['sha256']
    try:
        snapshot(tmp_path, 'run1', 'before')
    except FileExistsError:
        pass
    else:
        raise AssertionError('snapshot unexpectedly overwrote an existing run stage')
