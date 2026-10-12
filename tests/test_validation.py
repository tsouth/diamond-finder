from aurelinne_import import parse as parse_aurelinne
from criteria import dutch_shortlist_candidate, preference_flags, quality_status, ranking_components, shape_status
from mikado_probe import parse as parse_mikado
from calavera_probe import parse as parse_calavera
from calavera_details import inspect as inspect_calavera


CONFIRMED = dict(
    retailer='Aurelinne',
    carat=4.26,
    color='E',
    clarity='VVS1',
    length_mm=15.66,
    width_mm=7.96,
    ratio=1.967,
    depth_pct=64.4,
    table_pct=62,
    polish='Excellent',
    symmetry='Excellent',
    shape='Hexagonal Modified Brilliant',
    title='Hexagonal Modified Brilliant',
)


def test_confirmed_stone_passes_numerical_gates():
    assert quality_status(CONFIRMED) == 'PASS numerical criteria'
    assert shape_status(CONFIRMED).startswith('HEXAGONAL MODIFIED BRILLIANT')


def test_modified_brilliant_allowed_step_cut_excluded():
    brilliant = dict(CONFIRMED)
    step = dict(CONFIRMED, shape='Hexagonal Modified Step Cut', title='IGI Hexagonal Modified Step Cut')
    hexagonal_only = dict(CONFIRMED, shape='Hexagonal', title='4.26 ct. E/VVS1 Hexagonal Lab Grown Diamond')
    assert 'accept' in shape_status(brilliant).lower()
    assert shape_status(step).startswith('EXCLUDED')
    assert not dutch_shortlist_candidate(step)
    assert 'unverified' in shape_status(hexagonal_only).lower()


def test_mikado_missing_polish_is_pending_not_pass():
    row = dict(CONFIRMED, retailer='Mikado Diamonds', polish='', symmetry='', depth_pct='', table_pct='')
    assert quality_status(row) == 'PENDING missing specifications'


def test_regular_aurelinne_marquise_excluded_from_shortlist():
    row = dict(CONFIRMED, retailer='Aurelinne', shape='MARQUISE', title='Marquise')
    assert 'REGULAR MARQUISE' in shape_status(row)
    assert not dutch_shortlist_candidate(row)


def test_aurelinne_importer_reads_report_and_supplier_stock():
    records = [{
        'id': '20d7d351-a10a-48e7-b9cb-e006e2de67ff',
        'price': 1117,
        'title': 'Lab diamond',
        'supplierStockId': 'E2B25B2BD',
        'topImage': '',
        'certificate': {'number': 'LG825678759', 'v360': {'url': ''}},
        'description': (
            '<li>Carat: 4.26</li><li>Colour: E</li><li>Clarity: VVS1</li>'
            '<li>Shape: Hexagonal Modified Brilliant</li>'
            '<li>Measurements: 15.66 x 7.96 x 5.13</li>'
            '<li>L/W Ratio: 1.97</li><li>Depth: 64.4%</li><li>Table: 62%</li>'
            '<li>Polish: Excellent</li><li>Symmetry: Excellent</li>'
            '<li>Certificate Number: LG825678759</li>'
        ),
    }]
    rows = parse_aurelinne(records)
    assert rows[0]['certificate_number'] == 'LG825678759'
    assert rows[0]['supplier_stock_id'] == 'E2B25B2BD'
    assert rows[0]['match_target'].startswith('YES')


def test_mikado_parser_extracts_igi_and_does_not_trust_hexagonal_label():
    payload = {'products': [{
        'id': 8180131627140,
        'title': '4.26 ct. E/VVS1 Hexagonal Lab Grown Diamond',
        'body_html': '<p>IGI LG825678759</p><p>Measurements: 15.66 x 7.96 x 5.13 mm</p>',
        'tags': 'LGNE2B25B2BD',
        'handle': '4-26-ct-e-vvs1-hexagonal-lab-grown-diamond-3dbe8d97',
        'variants': [{'available': True, 'price': '2170.00', 'sku': 'LGNE2B25B2BD'}],
        'images': [],
        'image': {},
    }]}
    rows = parse_mikado(payload)
    assert rows[0]['certificate'] == 'LG825678759'
    assert rows[0]['supplier_stock_id'] == 'E2B25B2BD'
    assert 'facet' in rows[0]['shape'].lower() or 'unverified' in rows[0]['shape_verified'].lower()
    assert 'STEP CUT' not in rows[0]['shape'].upper()


def test_calavera_parser_preserves_hexagonal_as_unverified():
    payload = (
        'a:["$","$Lx",null,{"ref":"$undefined",'
        '"href":"/diamonds/4-00ct-hexagonal-lab-grown-diamond-colour-e-clarity-vvs1-igi-certified-'
        'ab3a1cf5-8423-4dae-8936-0694a03b7ca1",'
        '"title":"4.00ct Hexagonal Lab Diamond","amount":1117,"currencyCode":"USD"}'
    )
    rows = parse_calavera(payload)
    assert rows[0]['shape'] == 'Hexagonal'
    assert 'inspect IGI' in rows[0]['shape_verified']


def test_calavera_detail_reads_embedded_igi_specs():
    raw = r'''<script>{\"certificate\":{\"lab\":\"IGI\",\"shape\":\"HEXAGONAL\",\"number\":\"LG815654825\",\"pdfUrl\":\"https://example.test/LG815654825.pdf\"},\"polish\":\"Excellent\",\"symmetry\":\"Excellent\",\"ratio\":1.79,\"tablePct\":66,\"depthPct\":69.4,\"lengthMm\":13.63,\"widthMm\":7.62,\"depthMm\":5.29}</script>'''
    result = inspect_calavera({}, raw)
    assert result['lab'] == 'IGI'
    assert result['certificate'] == '815654825'
    assert result['length_mm'] == '13.63'
    assert result['table_pct'] == '66'
    assert result['polish'] == 'Excellent'
    assert result['review_status'].startswith('IGI FOUND')


def test_table_depth_and_borderline_ratio_are_soft_flags():
    row = dict(CONFIRMED, carat=4.45, ratio=1.89, depth_pct=67.4, table_pct=65.5)
    status = quality_status(row)
    assert status.startswith('PASS with preference flags')
    flags = preference_flags(row)
    assert any('ratio' in flag for flag in flags)
    assert any('depth' in flag for flag in flags)
    assert any('table' in flag for flag in flags)


def test_ranking_components_do_not_claim_optical_quality():
    row = dict(CONFIRMED, cutting_style_status='verified_igi', visual_review_status='pending', effective_price_usd='1117.00')
    score = ranking_components(row)
    assert score['dimension_fit'] is not None
    assert score['evidence_penalty'] == 1.0
    assert 0 <= score['overall'] <= 100
    assert score['overall'] <= score['dimension_fit']
