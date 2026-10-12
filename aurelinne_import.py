"""Import an authorized, locally saved Aurelinne diamond-search JSON response.

Usage: py aurelinne_import.py --response aurelinne_response.json
No credentials, cookies, or unverified API endpoints are required.
"""
import argparse
import csv
import json
import re
from pathlib import Path
from html import unescape

from criteria import dimension_score, quality_status
from identity import extract_report, extract_supplier_id, normalize_report
from storage import CURRENT, ensure_layout

FIELDS = ['retailer','id','carat','color','clarity','shape','length_mm','width_mm','height_mm','lw_ratio','depth_pct','table_pct','polish','symmetry','fluorescence','lab','certificate_number','supplier_stock_id','price','image_url','video_url','match_target','score','title']


def detail(description, name):
    pattern = r'<li>\s*' + re.escape(name) + r':\s*([^<]+)</li>'
    m = re.search(pattern, unescape(description or ''), flags=re.I)
    return m.group(1).strip() if m else ''


def number(value):
    try:
        return float(str(value).replace('%','').strip())
    except (ValueError, TypeError):
        return None


def extract(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ('diamonds','items','results','data','products'):
            if k in payload:
                try:
                    return extract(payload[k])
                except ValueError:
                    pass
    raise ValueError('Expected a list of diamond objects or a wrapper with data/items/results/diamonds.')


def parse(records):
    rows=[]
    for r in records:
        if not isinstance(r, dict) or not ('description' in r and 'id' in r):
            continue
        cert_raw = r.get('certificate')
        cert = cert_raw if isinstance(cert_raw, dict) else {}
        description = r.get('description') or ''
        dimensions = detail(description,'Measurements')
        match = re.search(r'([\d.]+)\s*[x×]\s*([\d.]+)\s*[x×]\s*([\d.]+)',dimensions,re.I)
        length, width, height = (map(float, match.groups()) if match else (None, None, None))
        carat = number(detail(description,'Carat')) or number(cert.get('carats'))
        color = detail(description,'Colour') or cert.get('color','')
        clarity = detail(description,'Clarity') or cert.get('clarity','')
        shape = detail(description,'Shape') or cert.get('shape','')
        lw = number(detail(description,'L/W Ratio')) or (round(length/width,3) if length and width else None)
        depth = number(detail(description,'Depth'))
        table = number(detail(description,'Table'))
        polish = detail(description,'Polish')
        symmetry = detail(description,'Symmetry')
        certificate_number = extract_report(
            detail(description, 'Certificate Number'),
            cert.get('number'), cert.get('certNumber'), cert.get('report_number'),
            cert.get('id'), cert_raw if isinstance(cert_raw, str) else '',
        ) or normalize_report(detail(description, 'Certificate Number'))
        supplier_stock_id = extract_supplier_id(r.get('supplierStockId'), r.get('sku'))
        scored = dict(carat=carat, color=color, clarity=clarity, length_mm=length, width_mm=width,
                      ratio=lw, depth_pct=depth, table_pct=table, polish=polish, symmetry=symmetry)
        in_range = quality_status(scored).startswith('PASS')
        score = dimension_score(length, width) or None
        if score is not None:
            score = float(score)
        rows.append(dict(retailer='Aurelinne',id=r['id'],carat=carat,color=color,clarity=clarity,shape=shape,length_mm=length,width_mm=width,height_mm=height,lw_ratio=lw,depth_pct=depth,table_pct=table,polish=polish,symmetry=symmetry,fluorescence=detail(description,'Fluorescence'),lab=detail(description,'Certificate') or cert.get('lab',''),certificate_number=certificate_number,supplier_stock_id=supplier_stock_id,price=r.get('price'),image_url=r.get('topImage',''),video_url=(cert.get('v360') or {}).get('url',''),match_target='YES - verify outline visually' if in_range else 'NO',score=score,title=r.get('title','')))
    return sorted(rows,key=lambda r:(r['match_target'].startswith('NO'),r['score'] if r['score'] is not None else float('inf')))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--response',required=True,help='Local JSON response saved from your browser')
    ap.add_argument('--output',default=str(CURRENT/'aurelinne_diamonds.csv'))
    args=ap.parse_args()
    ensure_layout();payload=json.loads(Path(args.response).read_text(encoding='utf-8-sig'))
    rows=parse(extract(payload))
    with open(args.output,'w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f'Parsed {len(rows)} diamonds; {sum(r["match_target"].startswith("YES") for r in rows)} pass numerical filters. Wrote {args.output}')
    if rows:
        print('Carat range:',min(r['carat'] for r in rows if r['carat'] is not None),'-',max(r['carat'] for r in rows if r['carat'] is not None))
        print('Shape labels:',sorted(set(r['shape'] for r in rows)))
    print('Shape label Other is NOT confirmation of Dutch marquise. Review imagery and certification.')

if __name__=='__main__':main()
