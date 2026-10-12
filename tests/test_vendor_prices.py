from vendor_prices import VENDORS, inspect_response, product_links, run


class Response:
    ok = True
    status_code = 200
    url = 'https://shop.test/search?q=LG825678759'
    text = '<form>LG825678759</form><div>From $700</div>'


def test_search_page_echo_is_not_itself_a_verified_product_result():
    assert product_links(Response.text, Response.url, 'LG825678759') == []


def test_certificate_linked_product_is_discovered():
    html = '<a href="/diamonds/stone-1">IGI LG825678759 · view diamond</a>'
    assert product_links(html, 'https://shop.test/search', 'LG825678759') == [
        'https://shop.test/diamonds/stone-1'
    ]


def test_product_response_can_return_a_price():
    response = Response()
    response.url = 'https://shop.test/diamonds/stone-1'
    response.text = '<h1>LG825678759</h1><meta property="product:price:amount" content="1117.00">'
    result = inspect_response('LG825678759', response, response.url)
    assert result['status'] == 'priced'
    assert result['price'] == '1117.00'


def test_offline_run_returns_one_explicit_result_per_vendor():
    rows = run(['LG825678759'], [], live=False)
    assert len(rows) == len(VENDORS) == 11
    assert {row['status'] for row in rows} == {'offline_not_checked'}
