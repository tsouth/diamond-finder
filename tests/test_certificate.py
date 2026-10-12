from identity import assign_match_groups, extract_report, extract_supplier_id, normalize_report, normalize_supplier_id
from cross_retailer_prices import apply_overrides, enrich_prices, same_stone_comparisons


def test_report_aliases_are_the_same_stone():
    assert normalize_report('LG825678759') == 'LG825678759'
    assert normalize_report('825678759') == 'LG825678759'
    assert extract_report('IGI LG825678759') == 'LG825678759'
    assert extract_report('IGI') == ''
    assert normalize_report('IGI') == ''


def test_supplier_stock_matches_mikado_sku():
    assert normalize_supplier_id('E2B25B2BD') == 'E2B25B2BD'
    assert normalize_supplier_id('LGNE2B25B2BD') == 'E2B25B2BD'
    assert extract_supplier_id('SKU LGNE2B25B2BD') == 'E2B25B2BD'
    assert normalize_supplier_id('8180131627140') == ''


def test_seeded_listings_form_one_price_group():
    rows = [
        {
            'retailer': 'Mikado Diamonds',
            'inventory_id': '8180131627140',
            'certificate': '',
            'supplier_stock_id': '',
            'price_usd': '2170',
            'shape': 'Hexagonal (facet unverified)',
            'title': '4.26 ct. E/VVS1 Hexagonal Lab Grown Diamond',
        },
        {
            'retailer': 'Aurelinne',
            'inventory_id': 'other',
            'certificate': '',
            'supplier_stock_id': '',
            'price_usd': '9999',
        },
    ]
    overrides = [
        {
            'retailer': 'Aurelinne',
            'inventory_id': '20d7d351-a10a-48e7-b9cb-e006e2de67ff',
            'certificate': 'LG825678759',
            'supplier_stock_id': 'E2B25B2BD',
            'price_usd': 1117,
            'shape': 'Hexagonal Modified Brilliant',
            'verification': 'User-supplied product API JSON, October 12 2026; price not checkout-verified',
        },
        {
            'retailer': 'Mikado Diamonds',
            'inventory_id': '8180131627140',
            'certificate': 'LG825678759',
            'supplier_stock_id': 'E2B25B2BD',
            'price_usd': 2170,
            'verification': 'User-supplied product listing and IGI report; price not checkout-verified',
        },
    ]
    apply_overrides(rows, overrides)
    enrich_prices(rows, '2026-10-12')
    comparisons = same_stone_comparisons(rows)
    pair = [c for c in comparisons if c['report'] == 'LG825678759']
    by_retailer = {c['retailer']: c for c in pair}
    assert set(by_retailer) >= {'Aurelinne', 'Mikado Diamonds'}
    assert str(by_retailer['Aurelinne']['listed_price_usd']) in {'1117', '1117.0'}
    assert by_retailer['Aurelinne']['effective_price_usd'] == '1005.30'
    assert by_retailer['Mikado Diamonds']['effective_price_usd'] == '2170.00'


def test_supplier_stock_matches_without_report_on_one_side():
    rows = [
        {'retailer': 'Aurelinne', 'certificate': 'LG825678759', 'supplier_namespace': 'shared_feed', 'supplier_stock_id': 'E2B25B2BD', 'price_usd': 1117},
        {'retailer': 'Mikado Diamonds', 'certificate': '', 'supplier_namespace': 'shared_feed', 'supplier_stock_id': 'LGNE2B25B2BD', 'price_usd': 2170},
    ]
    assign_match_groups(rows)
    assert rows[0]['duplicate_group'] == rows[1]['duplicate_group'] == 'LG825678759'
    assert rows[1]['normalized_report'] == 'LG825678759'


def test_supplier_stock_is_not_globally_unique():
    rows = [
        {'retailer': 'A', 'certificate': '', 'supplier_namespace': 'supplier_a', 'supplier_stock_id': 'ABC12345'},
        {'retailer': 'B', 'certificate': '', 'supplier_namespace': 'supplier_b', 'supplier_stock_id': 'ABC12345'},
        {'retailer': 'C', 'certificate': '', 'supplier_stock_id': 'ABC12345'},
    ]
    assign_match_groups(rows)
    assert all(not row['duplicate_group'] for row in rows)


def test_same_stock_with_conflicting_reports_never_matches():
    rows = [
        {'retailer': 'A', 'certificate': 'LG825678759', 'supplier_namespace': 'shared', 'supplier_stock_id': 'ABC12345'},
        {'retailer': 'B', 'certificate': 'LG841695845', 'supplier_namespace': 'shared', 'supplier_stock_id': 'ABC12345'},
    ]
    assign_match_groups(rows)
    assert all(not row['duplicate_group'] for row in rows)


def test_similar_dimensions_with_different_reports_do_not_match():
    rows = [
        {
            'retailer': 'Mikado Diamonds', 'certificate': 'LG825678759', 'supplier_stock_id': 'E2B25B2BD',
            'length_mm': 15.66, 'width_mm': 7.96, 'carat': 4.26, 'price_usd': 2170,
        },
        {
            'retailer': 'Aurelinne', 'certificate': 'LG111111111', 'supplier_stock_id': 'ZZZZZZZZZ',
            'length_mm': 15.66, 'width_mm': 7.96, 'carat': 4.26, 'price_usd': 1117,
        },
    ]
    assign_match_groups(rows)
    assert not rows[0]['duplicate_group']
    assert not rows[1]['duplicate_group']
