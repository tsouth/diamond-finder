"""Shared paths and UTF-8 CSV/JSON persistence for Diamond Finder."""
from __future__ import annotations

import csv
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG = BASE / 'config'
DATA = BASE / 'data'
CURRENT = DATA / 'current'
RAW = DATA / 'raw'
REFERENCE = DATA / 'reference'
RUNS = DATA / 'runs'
REPORTS = BASE / 'reports'
EVIDENCE = DATA / 'evidence'
CERTIFICATES = EVIDENCE / 'certificates'
OPTICAL = EVIDENCE / 'optical'


def ensure_layout() -> None:
    for path in (CONFIG, CURRENT, RAW, REFERENCE, RUNS, REPORTS, CERTIFICATES, OPTICAL):
        path.mkdir(parents=True, exist_ok=True)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0]) if rows else [])
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        if fields:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
            writer.writeheader(); writer.writerows(rows)


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
