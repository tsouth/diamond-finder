"""Acquire, import, parse, and validate IGI reports without trusting retailer labels.

Direct PDF retrieval is attempted first. Playwright is an optional fallback for the
normal public verification flow; it does not bypass CAPTCHAs or access controls.
Manual PDF import is always supported and is the most reliable fallback.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests

from identity import extract_report
from storage import CERTIFICATES, ensure_layout, read_json, write_json


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError('Install pypdf: py -m pip install pypdf') from exc
    return '\n'.join(page.extract_text() or '' for page in PdfReader(str(path)).pages)


def parse_report_text(text: str) -> dict:
    flat = re.sub(r'\s+', ' ', text).upper()
    def first(pattern, cast=str):
        match = re.search(pattern, flat, re.I)
        return cast(match.group(1)) if match else ''
    measurements = re.search(r'(\d{1,2}\.\d{1,2})\s*[X×]\s*(\d{1,2}\.\d{1,2})\s*[X×]\s*(\d{1,2}\.\d{1,2})\s*MM', flat)
    dims = [float(value) for value in measurements.groups()] if measurements else ['', '', '']
    summary = re.search(r'(?:FL|IF|VVS\s*[12]|VS\s*[12]|SI\s*[12]|I\s*[123])\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%', flat)
    return {
        'certificate': extract_report(first(r'(?:REPORT (?:NUMBER|NO\.?)[ :]*)?(LG\s*\d{6,12})')),
        'cutting_style': first(r'SHAPE AND CUTTING STYLE\s+(.+?)(?=\s+MEASUREMENTS)'),
        'length_mm': dims[0], 'width_mm': dims[1], 'height_mm': dims[2],
        'carat': first(r'CARAT WEIGHT\s+(\d+(?:\.\d+)?)\s*CARAT', float),
        'color': first(r'COLOR GRADE\s+([D-Z])(?:\s|$)'),
        'clarity': first(r'CLARITY GRADE\s+(FL|IF|VVS\s*[12]|VS\s*[12]|SI\s*[12]|I\s*[123])').replace(' ', ''),
        'table_pct': float(summary.group(2)) if summary else first(r'(\d+(?:\.\d+)?)%\s+(?:TABLE|TABLE SIZE)', float),
        'depth_pct': float(summary.group(1)) if summary else first(r'(?:DEPTH|TOTAL DEPTH)\s+(\d+(?:\.\d+)?)%', float),
        'polish': first(r'POLISH\s+(EXCELLENT|VERY GOOD|GOOD|FAIR|POOR)'),
        'symmetry': first(r'SYMMETRY\s+(EXCELLENT|VERY GOOD|GOOD|FAIR|POOR)'),
        'fluorescence': first(r'FLUORESCENCE\s+(NONE|FAINT|MEDIUM|STRONG|VERY STRONG)'),
        'inscription': extract_report(first(r'INSCRIPTION(?:\(S\))?\s+([^|]+?LG\s*\d{6,12})')),
        'growth_method': first(r'CREATED BY\s+(.+?)\s+GROWTH PROCESS'),
        'report_date': first(r'([A-Z]+\s+\d{1,2},\s+\d{4})\s+IGI REPORT NUMBER'),
    }


def validate_fields(fields: dict, expected: dict) -> list[str]:
    mismatches = []
    report = extract_report(expected.get('certificate'))
    if fields.get('certificate') and fields['certificate'] != report:
        mismatches.append(f"report {fields['certificate']} != expected {report}")
    style = str(fields.get('cutting_style') or '').upper()
    if style and 'HEXAGONAL MODIFIED BRILLIANT' not in style:
        mismatches.append(f'cutting style is {style}')
    for key in ('carat', 'length_mm', 'width_mm', 'height_mm', 'table_pct', 'depth_pct'):
        actual, wanted = fields.get(key), expected.get(key)
        if actual not in ('', None) and wanted not in ('', None) and abs(float(actual) - float(wanted)) > 0.06:
            mismatches.append(f'{key} {actual} != expected {wanted}')
    for key in ('color', 'clarity', 'polish', 'symmetry'):
        actual, wanted = str(fields.get(key) or '').replace(' ', '').upper(), str(expected.get(key) or '').replace(' ', '').upper()
        if actual and wanted and actual != wanted:
            mismatches.append(f'{key} {actual} != expected {wanted}')
    return mismatches


def save_evidence(pdf: Path, report: str, source_url: str, expected: dict) -> dict:
    report = extract_report(report)
    target = CERTIFICATES / f'{report}.pdf'
    metadata_path = CERTIFICATES / f'{report}.json'
    if source_url.startswith('manual:') and metadata_path.exists():
        previous = read_json(metadata_path)
        if str(previous.get('source_url') or '').startswith('http'):
            source_url = previous['source_url']
    target.parent.mkdir(parents=True, exist_ok=True)
    if pdf.resolve() != target.resolve():
        shutil.copy2(pdf, target)
    fields = parse_report_text(extract_pdf_text(target))
    mismatches = validate_fields(fields, expected)
    required = ('certificate','cutting_style','length_mm','width_mm','height_mm','carat','color',
                'clarity','table_pct','depth_pct','polish','symmetry','inscription')
    missing = [key for key in required if fields.get(key) in ('', None)]
    evidence = {
        'certificate': report, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'source_url': source_url, 'pdf_path': target.relative_to(CERTIFICATES.parent.parent).as_posix(),
        'sha256': sha256(target), 'fields': fields, 'mismatches': mismatches, 'missing_fields': missing,
        'validation_status': 'validated' if fields.get('certificate') == report and not mismatches and not missing else 'conflict' if mismatches else 'incomplete',
    }
    write_json(metadata_path, evidence)
    return evidence


def direct_download(report: str, destination: Path) -> str:
    digits = re.sub(r'\D', '', report)
    urls = [f'https://pdf.igi.org/FDR{digits}.pdf', f'https://www.igi.org/viewpdf.php?r={report}']
    for url in urls:
        response = requests.get(url, timeout=30, headers={'User-Agent': 'DiamondFinder/17 report verification'})
        if response.ok and response.content.startswith(b'%PDF'):
            destination.write_bytes(response.content)
            return url
    return ''


def embedded_pdf_urls(html: str, source_url: str, report: str) -> list[str]:
    """Find likely certificate assets embedded in retailer HTML or JSON."""
    decoded = html.replace('\\/', '/').replace('&amp;', '&')
    raw = re.findall(r'''(?:href|src)[=:\s]*["']([^"']+)["']|https?://[^\s"'<>]+''', decoded, re.I)
    urls = []
    for match in raw:
        candidate = match if isinstance(match, str) else next((part for part in match if part), '')
        if not candidate:
            continue
        candidate = candidate.rstrip('),]}')
        absolute = urljoin(source_url, candidate)
        lowered = absolute.lower()
        if ('pdf' in lowered or re.sub(r'\D', '', report) in lowered) and absolute not in urls:
            urls.append(absolute)
    return urls


def retailer_download(source_url: str, report: str, destination: Path) -> str:
    try:
        page = requests.get(source_url, timeout=25, headers={'User-Agent': 'Mozilla/5.0 DiamondFinder/17'})
    except requests.RequestException:
        return ''
    if not page.ok:
        return ''
    for url in embedded_pdf_urls(page.text, source_url, report):
        try:
            response = requests.get(url, timeout=25, headers={'Referer': source_url, 'User-Agent': 'Mozilla/5.0'})
        except requests.RequestException:
            continue
        if response.ok and response.content.startswith(b'%PDF'):
            destination.write_bytes(response.content)
            return url
    return ''


def playwright_download(report: str, destination: Path) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError('Install Playwright and Chromium: py -m pip install playwright; playwright install chromium') from exc
    verify = f'https://www.igi.org/verify-your-report/?r={report}'
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel='msedge', headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        page = browser.new_page(accept_downloads=True)
        try:
            page.goto(verify, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(5000)
        except Exception:
            browser.close()
            return ''
        links = page.locator('a[href*="pdf"], a[href*="PDF"]')
        for index in range(links.count()):
            url = links.nth(index).get_attribute('href') or ''
            if url:
                response = page.request.get(url)
                body = response.body()
                if response.ok and body.startswith(b'%PDF'):
                    destination.write_bytes(body); browser.close(); return url
        browser.close()
    return ''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('certificate'); parser.add_argument('--import-pdf', type=Path)
    parser.add_argument('--expected', default='confirmed_listings.json'); parser.add_argument('--playwright', action='store_true')
    parser.add_argument('--source-url', action='append', default=[], help='Retailer page that may embed the report PDF')
    args = parser.parse_args(); ensure_layout(); report = extract_report(args.certificate)
    expected_rows = read_json(Path(__file__).parent / 'config' / args.expected)
    expected = next((row for row in expected_rows if extract_report(row.get('certificate')) == report), {'certificate': report})
    temp = CERTIFICATES / f'.{report}.download.pdf'
    if args.import_pdf:
        evidence = save_evidence(args.import_pdf, report, f'manual:{args.import_pdf}', expected)
    else:
        retailer_urls = args.source_url + [row.get('product_url','') for row in expected_rows if extract_report(row.get('certificate')) == report]
        source = next((found for url in retailer_urls if url and (found := retailer_download(url, report, temp))), '')
        if not source: source = direct_download(report, temp)
        if not source and args.playwright: source = playwright_download(report, temp)
        if not source: raise SystemExit('IGI PDF not retrieved. Download it manually and use --import-pdf PATH.')
        evidence = save_evidence(temp, report, source, expected); temp.unlink(missing_ok=True)
    print(f"{report}: {evidence['validation_status']} ({len(evidence['mismatches'])} mismatch(es))")


if __name__ == '__main__': main()
