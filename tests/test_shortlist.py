import json
from pathlib import Path

from provenance import snapshot
from shortlist import build, qualification_status
from storage import CONFIG


ROOT = Path(__file__).resolve().parents[1]


def seeded_rows():
    return json.loads((CONFIG / 'confirmed_listings.json').read_text(encoding='utf-8'))


def test_shortlist_has_five_physical_diamonds_and_seven_offers():
    diamonds, offers, nested = build(seeded_rows(), '2026-10-12')
    assert len(diamonds) == 5
    assert len(offers) == 7
    assert len(nested) == 5


def test_computed_ranking_matches_provisional_top_five():
    diamonds, _, _ = build(seeded_rows(), '2026-10-12')
    assert [row['certificate'] for row in diamonds] == [
        'LG825678759', 'LG841695845', 'LG829618561', 'LG837626976', 'LG822610872'
    ]


def test_shared_diamond_keeps_both_offers_and_cheapest():
    diamonds, offers, _ = build(seeded_rows(), '2026-10-12')
    diamond = next(row for row in diamonds if row['certificate'] == 'LG825678759')
    shared = [row for row in offers if row['certificate'] == 'LG825678759']
    assert {row['retailer'] for row in shared} == {'Aurelinne', 'Mikado Diamonds', 'Ritani'}
    assert diamond['offer_count'] == 3
    assert diamond['cheapest_retailer'] == 'Aurelinne'
    assert diamond['cheapest_effective_price'] == '1005.30'


def test_exact_certificate_coverage_is_not_reported_as_live_price_coverage():
    evidence = {
        'coverage': json.loads((CONFIG / 'retailer_coverage.json').read_text(encoding='utf-8')),
        'optical': [], 'policies': [], 'certificates': {},
    }
    diamonds, _, _ = build(seeded_rows(), '2026-10-12', evidence)
    diamond = next(row for row in diamonds if row['certificate'] == 'LG825678759')
    assert diamond['exact_certificate_searched'] == 7
    assert diamond['retailer_universe'] == 11
    assert diamond['matching_active_offers'] == 3
    assert diamond['checkout_verified_offers'] == 0
    assert diamond['coverage_not_searched'] == 'Adiamor | Brilliance | With Clarity | Friendly Diamonds'


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
