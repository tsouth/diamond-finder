"""Normalize IGI report numbers and supplier stock IDs for same-stone matching."""
from __future__ import annotations

import re
from collections import defaultdict

LAB_ONLY = re.compile(r'^(?:IGI|GIA|HRD|WISE)$', re.I)
LAB_PREFIX = re.compile(r'^(?:IGI|GIA|HRD|WISE)\s*', re.I)
REPORT_CORE = re.compile(r'^(?:LG)?(\d{7,12})$')
NEAR_REPORT = re.compile(
    r'(?:IGI|GIA|HRD|report|certificate|cert(?:ificate)?\s*(?:number|no\.?)|#)\s*[:#-]?\s*'
    r'(?:IGI|GIA|HRD)?\s*(?:LG)?(\d{7,12})\b',
    re.I,
)
LG_REPORT = re.compile(r'\bLG(\d{7,12})\b', re.I)
LGN_SKU = re.compile(r'\bLGN([A-Z0-9]{5,16})\b', re.I)
STOCK_ID = re.compile(r'^[A-Z0-9]{6,16}$')


def normalize_report(value) -> str:
    """Return LG-prefixed report id, or '' if value is only a lab name / not a report."""
    raw = str(value or '').strip().upper()
    if not raw or LAB_ONLY.fullmatch(raw):
        return ''
    compact = re.sub(r'[\s\-]', '', LAB_PREFIX.sub('', raw))
    match = REPORT_CORE.fullmatch(compact)
    return 'LG' + match.group(1) if match else ''


def extract_report(*values) -> str:
    """Prefer labeled/LG report numbers; never treat a bare lab name as a certificate."""
    for value in values:
        direct = normalize_report(value)
        if direct:
            return direct
        text = str(value or '')
        labeled = NEAR_REPORT.search(text)
        if labeled:
            return normalize_report(labeled.group(1))
        lg = LG_REPORT.search(text)
        if lg:
            return normalize_report(lg.group(1))
    return ''


def normalize_supplier_id(value) -> str:
    """Mikado SKU LGNE2B25B2BD and Aurélinne supplierStockId E2B25B2BD are the same stone."""
    s = re.sub(r'[\s\-]', '', str(value or '').strip().upper())
    if s.startswith('LGN') and len(s) > 5:
        s = s[3:]
    if not s or s.isdigit():
        return ''
    return s if STOCK_ID.fullmatch(s) else ''


def extract_supplier_id(*values) -> str:
    for value in values:
        found = LGN_SKU.search(str(value or ''))
        if found:
            return found.group(1).upper()
        direct = normalize_supplier_id(value)
        if direct:
            return direct
    return ''


def supplier_match_key(row: dict) -> tuple[str, str] | None:
    """Supplier IDs are comparable only inside an explicit supplier namespace."""
    namespace = str(row.get('supplier_namespace') or '').strip().casefold()
    stock = extract_supplier_id(row.get('supplier_stock_id'), row.get('sku'))
    return (namespace, stock) if namespace and stock else None


def _find(parent, i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def assign_match_groups(rows: list[dict]) -> list[dict]:
    """Union listings that share a report number or a supplier stock id."""
    parent = list(range(len(rows)))

    def union(i, j):
        a, b = _find(parent, i), _find(parent, j)
        if a != b:
            parent[b] = a

    by_report, by_stock = {}, {}
    for i, row in enumerate(rows):
        report = extract_report(row.get('certificate'), row.get('certificate_number'))
        stock = extract_supplier_id(row.get('supplier_stock_id'), row.get('sku'))
        stock_key = supplier_match_key(row)
        row['normalized_report'] = report
        if stock and not extract_supplier_id(row.get('supplier_stock_id')):
            row['supplier_stock_id'] = stock
        elif stock:
            row['supplier_stock_id'] = stock
        else:
            row.setdefault('supplier_stock_id', row.get('supplier_stock_id') or '')
        if report:
            if report in by_report:
                union(i, by_report[report])
            else:
                by_report[report] = i
        if stock_key:
            if stock_key in by_stock:
                other = by_stock[stock_key]
                other_report = rows[other].get('normalized_report')
                if not (report and other_report and report != other_report):
                    union(i, other)
            else:
                by_stock[stock_key] = i

    buckets = defaultdict(list)
    for i in range(len(rows)):
        buckets[_find(parent, i)].append(i)

    for members in buckets.values():
        reports = {rows[i]['normalized_report'] for i in members if rows[i].get('normalized_report')}
        stocks = {extract_supplier_id(rows[i].get('supplier_stock_id')) for i in members}
        stocks.discard('')
        report = next(iter(reports)) if len(reports) == 1 else ''
        stock = next(iter(stocks)) if len(stocks) == 1 else ''
        retailers = {str(rows[i].get('retailer') or '') for i in members}
        cross = len(retailers) > 1 and len(members) > 1
        label = report or (('stock:' + stock) if stock and cross else '')
        for i in members:
            if report and not rows[i].get('normalized_report'):
                rows[i]['normalized_report'] = report
            if stock and not extract_supplier_id(rows[i].get('supplier_stock_id')):
                rows[i]['supplier_stock_id'] = stock
            rows[i]['duplicate_group'] = label if cross else rows[i].get('duplicate_group', '')
            if not rows[i].get('duplicate_group'):
                rows[i]['duplicate_group'] = ''
    return rows
