from render_report import render


def test_report_renders_sortable_diamond_and_offer():
    data = [{
        'computed_rank': 1, 'certificate': 'LG825678759', 'certificate_url': 'https://igi.test/report',
        'carat': 4.26, 'color': 'E', 'clarity': 'VVS1', 'length_mm': 15.66, 'width_mm': 7.96,
        'height_mm': 5.13, 'ratio': 1.967, 'table_pct': 62, 'depth_pct': 64.4,
        'overall_score': 2.1, 'dimension_fit_score': .849, 'preference_penalty': 0,
        'visual_review_status': 'pending', 'cheapest_effective_price': '1005.30',
        'cheapest_retailer': 'Aurelinne', 'offer_count': 1, 'warnings': 'optical review pending',
        'offers': [{'retailer':'Aurelinne','effective_price_usd':'1005.30','listed_price':'1117.00',
                    'currency':'USD','observed_at':'2026-10-12','promo_status':'estimated_unverified',
                    'promo_code':'FALL10','product_url':'https://example.test','image_url':'','video_url':''}],
    }]
    page = render(data, '2026-10-12')
    assert 'LG825678759' in page
    assert '$1,005.30' in page
    assert 'FALL10' in page
    assert 'id="sort"' in page
    assert 'How the rankings are calculated' in page
    assert 'View this stone and compare 1 offers' in page
    assert '<h3>IGI report</h3>' not in page
    assert '<h3>Retailers checked</h3>' not in page
    assert 'Diamond score' in page and 'Value score' in page
    assert 'Neither score predicts brilliance' in page
