from heart_side_stones import CENTER, aurelinne_payload, pair_score, rank_pairs, report_html, scale_svg, screen


BASE = {'shape':'Heart Brilliant','carat':.60,'color':'E','clarity':'VS1','length_mm':4.75,
        'width_mm':5.0,'ratio':.95,'table_pct':61,'depth_pct':57,'polish':'Excellent',
        'symmetry':'Excellent','certificate':'LG100000001','video_url':'https://video.test/1'}


def test_igi_heart_ranges_pass_without_proportion_warning():
    _, failures, warnings, fit = screen(BASE)
    assert failures == []
    assert not any('outside IGI' in warning for warning in warnings)
    assert fit < 100


def test_pair_matching_penalizes_dimension_mismatch():
    close = {**BASE, 'certificate':'LG100000002','width_mm':5.02,'length_mm':4.77,'carat':.61}
    far = {**BASE, 'certificate':'LG100000003','width_mm':5.35,'length_mm':4.8,'carat':.72}
    assert pair_score(BASE, close) is not None
    assert pair_score(BASE, far) is None


def test_pair_ranking_is_separate_and_descending():
    rows=[BASE,{**BASE,'certificate':'LG2','width_mm':5.01},{**BASE,'certificate':'LG3','width_mm':5.02}]
    pairs=rank_pairs(rows)
    assert pairs[0]['pair_score'] >= pairs[-1]['pair_score']
    assert all('overall_score' not in pair for pair in pairs)


def test_scale_svg_uses_center_actual_dimensions_and_physical_units():
    svg=scale_svg(5.0)
    assert 'mm" height=' in svg
    assert '15.660' in svg
    assert '5.0 mm hearts' in svg
    assert 'points face west/east' in svg
    assert '0.15 mm clearance' in svg


def test_report_explains_scale_and_no_inventory():
    page=report_html([])
    assert CENTER['certificate'] in page
    assert 'True-scale plan renderings' in page
    assert 'Inventory has not been collected' in page
    assert 'This does not mean the market was fully searched' in page
    assert 'Print at 100%' in page
    assert 'Left point faces west; right point faces east' in page


def test_aurelinne_discovery_is_broad_and_paginated():
    payload=aurelinne_payload(540)
    assert payload['offset'] == 540
    assert payload['query']['shapes'] == ['HEART']
    assert 'symmetry' not in payload['query']


def test_borderline_example_remains_visible_for_review():
    example={**BASE,'length_mm':5.39,'width_mm':5.39,'ratio':1.0,'symmetry':'Good'}
    _, failures, warnings, _=screen(example)
    assert failures == []
    assert any('symmetry Good' in warning for warning in warnings)
    assert not any('ratio 1' in warning for warning in warnings)


def test_pair_requires_matching_color_clarity_ratio_and_proportions():
    assert pair_score(BASE,{**BASE,'certificate':'LG2','color':'D'}) is None
    assert pair_score(BASE,{**BASE,'certificate':'LG2','clarity':'VVS2'}) is None
    assert pair_score(BASE,{**BASE,'certificate':'LG2','ratio':1.0}) is None
    table_spread=pair_score(BASE,{**BASE,'certificate':'LG2','table_pct':64})
    assert table_spread is not None
    assert any('table_pct difference' in warning for warning in table_spread['warnings'])


def test_center_compatible_grade_window_and_tight_size_gate():
    assert screen({**BASE,'color':'F','clarity':'VS1'})[1] == []
    assert 'clarity below VS1' in screen({**BASE,'clarity':'VS2'})[1]
    assert pair_score(BASE,{**BASE,'certificate':'LG2','length_mm':4.80}) is not None
    assert pair_score(BASE,{**BASE,'certificate':'LG2','length_mm':4.81}) is None


def test_face_up_match_is_not_rejected_by_weight_or_proportion_spread():
    first={**BASE,'certificate':'LG783603221','carat':.56,'length_mm':5.38,'width_mm':5.38,
           'ratio':1.0,'table_pct':59,'depth_pct':61,'color':'D','clarity':'VVS2'}
    second={**BASE,'certificate':'LG784671182','carat':.52,'length_mm':5.39,'width_mm':5.39,
            'ratio':1.0,'table_pct':62,'depth_pct':59.2,'color':'D','clarity':'VVS2','symmetry':'Good'}
    pair=pair_score(first,second)
    assert pair is not None
    assert pair['pair_score'] > 90
    assert any('carat difference' in warning for warning in pair['warnings'])
