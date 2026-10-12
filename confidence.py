"""Auditable evidence, freshness, and purchase-readiness rules."""
from __future__ import annotations

from datetime import date, datetime

from identity import extract_report
from pricing import money

FINAL_OPTICAL = {'pass', 'pass_with_notes'}
AVAILABLE = {'available', 'in stock', 'live', 'confirmed'}


def _date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def offer_freshness(offer: dict, as_of: str, fresh_days: int = 7, stale_days: int = 30) -> dict:
    observed = _date(offer.get('last_checked_at') or offer.get('observed_at'))
    today = _date(as_of) or date.today()
    if not observed:
        return {'age_days': '', 'freshness_status': 'unknown', 'eligible_live_offer': False}
    age = (today - observed).days
    status = 'fresh' if age <= fresh_days else 'aging' if age <= stale_days else 'stale'
    availability = str(offer.get('availability') or '').strip().lower()
    live = status == 'fresh' and availability in AVAILABLE and money(
        offer.get('effective_price_usd') or offer.get('listed_price')) is not None
    return {'age_days': age, 'freshness_status': status, 'eligible_live_offer': live}


def optical_summary(review: dict | None) -> dict:
    review = review or {}
    required = ('outline', 'faceting', 'bow_tie', 'central_darkness', 'tips',
                'windowing', 'symmetry', 'tilt_performance')
    missing = [field for field in required if not review.get(field)]
    decision = str(review.get('decision') or 'pending').lower()
    return {
        'optical_review_status': decision,
        'optical_review_complete': not missing and decision in FINAL_OPTICAL,
        'optical_confidence': review.get('confidence', 'unrated'),
        'optical_reviewer': review.get('reviewer', ''),
        'optical_reviewed_at': review.get('reviewed_at', ''),
        'optical_missing_fields': ', '.join(missing),
        'optical_notes': review.get('notes', ''),
        'optical_review': review,
    }


def certificate_summary(evidence: dict | None) -> dict:
    evidence = evidence or {}
    mismatches = evidence.get('mismatches') or []
    status = evidence.get('validation_status') or 'missing'
    return {
        'certificate_evidence_status': status,
        'certificate_source': evidence.get('source_url', ''),
        'certificate_file': evidence.get('pdf_path', ''),
        'certificate_sha256': evidence.get('sha256', ''),
        'certificate_checked_at': evidence.get('retrieved_at', ''),
        'certificate_mismatches': '; '.join(mismatches),
        'certificate_missing_fields': ', '.join(evidence.get('missing_fields') or []),
        'certificate_fields': evidence.get('fields', {}),
    }


def readiness(diamond: dict, offers: list[dict], policy: dict | None = None) -> tuple[str, list[str]]:
    blockers = []
    qualification = str(diamond.get('qualification_status') or '')
    if qualification.startswith('REJECT'):
        return 'NOT READY', [qualification]
    if diamond.get('certificate_evidence_status') != 'validated':
        blockers.append('retained IGI report has not been validated')
    if diamond.get('certificate_mismatches'):
        blockers.append('certificate conflicts require resolution')
    if not diamond.get('optical_review_complete'):
        blockers.append('structured optical review is incomplete')
    live = [offer for offer in offers if offer.get('eligible_live_offer')]
    if not live:
        blockers.append('no fresh, confirmed-available offer')
    if not policy or not policy.get('return_policy_verified_at'):
        blockers.append('seller protection terms are not recorded')
    if blockers:
        if diamond.get('certificate_evidence_status') == 'validated':
            return 'READY FOR VENDOR QUESTIONS', blockers
        return 'NOT READY', blockers
    if not any(o.get('checkout_verified_at') for o in live):
        return 'READY FOR CHECKOUT VERIFICATION', ['final checkout total not recorded']
    return 'READY TO PURCHASE', []


def index_by_report(rows: list[dict]) -> dict[str, dict]:
    return {extract_report(row.get('certificate')): row for row in rows if extract_report(row.get('certificate'))}
