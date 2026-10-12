from confidence import offer_freshness, optical_summary, readiness
from igi_report import embedded_pdf_urls, parse_report_text, validate_fields


def test_offer_must_be_recent_and_explicitly_available():
    fresh = offer_freshness({'observed_at':'2026-10-10','availability':'available','listed_price':'1000'}, '2026-10-12')
    stale = offer_freshness({'observed_at':'2026-08-01','availability':'available','listed_price':'1000'}, '2026-10-12')
    unknown = offer_freshness({'observed_at':'2026-10-10','availability':'historical snapshot','listed_price':'1000'}, '2026-10-12')
    assert fresh['eligible_live_offer'] is True
    assert stale['freshness_status'] == 'stale' and stale['eligible_live_offer'] is False
    assert unknown['eligible_live_offer'] is False


def test_optical_review_requires_every_observation_and_decision():
    incomplete = optical_summary({'decision':'pass','outline':'dutch'})
    complete = optical_summary({
        'decision':'pass', 'outline':'dutch', 'faceting':'brilliant', 'bow_tie':'minor',
        'central_darkness':'none', 'tips':'active', 'windowing':'none',
        'symmetry':'balanced', 'tilt_performance':'acceptable'})
    assert incomplete['optical_review_complete'] is False
    assert complete['optical_review_complete'] is True


def test_readiness_never_uses_ranking_as_evidence():
    diamond = {'qualification_status':'CERTIFICATE QUALIFIED', 'overall_score':0.1,
               'certificate_evidence_status':'missing', 'optical_review_complete':False}
    status, blockers = readiness(diamond, [], None)
    assert status == 'NOT READY'
    assert any('IGI' in item for item in blockers)


def test_igi_text_parser_and_mismatch_detection():
    text = '''IGI Report Number LG825678759 Shape and Cutting Style HEXAGONAL MODIFIED BRILLIANT
    Measurements 15.66 X 7.96 X 5.13 MM Carat Weight 4.26 CARATS Color Grade E
    Clarity Grade VVS 1 Polish EXCELLENT Symmetry EXCELLENT Fluorescence NONE'''
    fields = parse_report_text(text)
    expected = {'certificate':'LG825678759','carat':4.26,'color':'E','clarity':'VVS1',
                'length_mm':15.66,'width_mm':7.96,'height_mm':5.13,
                'polish':'Excellent','symmetry':'Excellent'}
    assert fields['certificate'] == 'LG825678759'
    assert fields['cutting_style'] == 'HEXAGONAL MODIFIED BRILLIANT'
    assert validate_fields(fields, expected) == []
    assert validate_fields(fields, {**expected, 'width_mm':8.2})


def test_embedded_retailer_certificate_pdf_discovery():
    html = '<a href="/certificates/LG825678759.pdf">report</a>'
    assert embedded_pdf_urls(html, 'https://retailer.test/stone', 'LG825678759') == [
        'https://retailer.test/certificates/LG825678759.pdf'
    ]
