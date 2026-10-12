"""Immutable, timestamped snapshots for auditing collector inputs and outputs."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

TRACKED_FILES = {
    'data/current/diamonds_enriched.csv', 'data/current/aurelinne_diamonds.csv',
    'data/current/calavera_diamonds.csv', 'data/current/calavera_other_details.csv',
    'data/current/mikado_diamonds.csv', 'config/confirmed_listings.json',
    'reports/master_diamond_comparison.csv', 'reports/dutch_marquise_review.csv',
    'reports/diamond_prices_with_promos.csv', 'reports/same_diamond_price_comparison.csv',
    'reports/ranked_shortlist.csv', 'reports/shortlist_offers.csv',
    'reports/dashboard_data.json', 'reports/diamond_report.html',
    'reports/retailer_coverage.csv', 'reports/exact_search_plan.json',
    'reports/vendor_price_checks.csv', 'reports/vendor_price_checks.json',
    'data/current/heart_side_stones.csv', 'reports/heart_side_stone_pairs.csv',
    'reports/heart_side_stone_pairs.json', 'reports/heart_side_stone_report.html',
    'reports/heart_layout_subtle.svg', 'reports/heart_layout_balanced.svg',
    'reports/heart_layout_bold.svg',
    'config/optical_reviews.json', 'config/retailer_coverage.json',
    'config/vendor_policies.json',
}
RAW_PATTERNS = (
    'data/raw/stienhardt/*', 'data/raw/aurelinne/*', 'data/raw/calavera/*',
    'data/raw/mikado/*',
    'data/evidence/certificates/*', 'data/evidence/optical/*',
)


def new_run_id(now=None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime('%Y%m%dT%H%M%SZ')


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def snapshot(base: Path, run_id: str, stage: str) -> Path:
    target = base / 'data' / 'runs' / run_id / stage
    target.mkdir(parents=True, exist_ok=False)
    sources = [base / name for name in TRACKED_FILES]
    for pattern in RAW_PATTERNS:
        sources.extend(base.glob(pattern))
    manifest = []
    seen = set()
    for source in sources:
        if not source.is_file() or source.resolve() in seen:
            continue
        seen.add(source.resolve())
        relative = source.relative_to(base)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        manifest.append({
            'path': relative.as_posix(), 'bytes': source.stat().st_size,
            'sha256': _sha256(source), 'modified_utc': datetime.fromtimestamp(
                source.stat().st_mtime, timezone.utc).isoformat(),
        })
    (target / 'manifest.json').write_text(
        json.dumps({'run_id': run_id, 'stage': stage, 'files': manifest}, indent=2),
        encoding='utf-8',
    )
    return target
