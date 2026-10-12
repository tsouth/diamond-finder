from pricing import FALL10, apply_promo


def test_fall10_estimated_effective_price():
    result = apply_promo(1117, 'Aurelinne', '2026-10-12', FALL10)
    assert result['effective_price_usd'] == '1005.30'
    assert result['promo_code'] == 'FALL10'
    assert result['promo_status'] == 'estimated_unverified'
    assert 'checkout' in result['price_status'].lower()


def test_promo_expires_after_end_date():
    result = apply_promo(1117, 'Aurelinne', '2026-11-01', FALL10)
    assert result['effective_price_usd'] == '1117.00'
    assert result['promo_code'] == ''
    assert result['promo_status'] == 'expired'


def test_non_aurelinne_rows_are_not_discounted():
    result = apply_promo(2170, 'Mikado Diamonds', '2026-10-12', FALL10)
    assert result['effective_price_usd'] == '2170.00'
    assert result['promo_code'] == ''
    assert result['promo_status'] == 'none'


def test_unverified_promo_is_not_treated_as_guaranteed():
    result = apply_promo(1117, 'Aurelinne', '2026-10-12')
    assert result['promo_status'] == 'estimated_unverified'
    assert FALL10.checkout_verified is False


def test_price_math_preserves_cents():
    result = apply_promo('1899.80', 'Mikado Diamonds', '2026-10-12')
    assert result['effective_price_usd'] == '1899.80'


def test_invalid_or_negative_price_is_missing():
    assert apply_promo('-1', 'Aurelinne', '2026-10-12')['effective_price_usd'] == ''
    assert apply_promo('not a price', 'Aurelinne', '2026-10-12')['effective_price_usd'] == ''
