"""Retailer promotions. Effective prices are estimates until checkout confirms them."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


@dataclass(frozen=True)
class Promo:
    retailer: str
    code: str
    discount: Decimal
    end: str
    checkout_verified: bool = False


FALL10 = Promo(
    retailer='Aurelinne',
    code='FALL10',
    discount=Decimal('0.10'),
    end='2026-10-31',
    checkout_verified=False,
)


def parse_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def numeric_price(value):
    try:
        return float(str(value).replace('$', '').replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def money(value) -> Decimal | None:
    try:
        amount = Decimal(str(value).replace('$', '').replace(',', '').strip())
        return amount if amount.is_finite() and amount >= 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def apply_promo(price, retailer, as_of, promo: Promo = FALL10) -> dict:
    listed = money(price)
    as_of_date = parse_date(as_of)
    end = parse_date(promo.end)
    same_retailer = str(retailer or '').strip().casefold() == promo.retailer.casefold()
    expired = as_of_date > end
    apply = same_retailer and listed is not None and not expired
    discount = promo.discount if apply else Decimal('0')
    if listed is None:
        effective = ''
    else:
        effective_value = (listed * (Decimal('1') - discount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        effective = f'{effective_value:.2f}'
    if apply and not promo.checkout_verified:
        status = 'Estimated with unverified promo; confirm at checkout'
        promo_status = 'estimated_unverified'
        code = promo.code
    elif apply and promo.checkout_verified:
        status = 'Promo applied; still confirm inventory at checkout'
        promo_status = 'applied'
        code = promo.code
    elif same_retailer and expired:
        status = 'Listed price; promo expired'
        promo_status = 'expired'
        code = ''
    else:
        status = 'Snapshot price; verify checkout'
        promo_status = 'none'
        code = ''
    return {
        'promo_code': code,
        'promo_discount_pct': f'{discount * 100:.2f}' if discount else '0',
        'effective_price_usd': effective,
        'price_status': status,
        'promo_status': promo_status,
    }
