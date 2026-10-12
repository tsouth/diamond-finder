"""Independent heart side-stone finder, pair matcher, and scale renderer."""
from __future__ import annotations

import argparse
import csv
import html
import itertools
import json
import math
import time
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from pathlib import Path

import requests

from aurelinne_import import extract as extract_aurelinne, parse as parse_aurelinne
from mikado_probe import parse as parse_mikado
from storage import CONFIG, CURRENT, RAW, REPORTS, ensure_layout, read_csv, read_json, write_csv, write_json
from vendor_prices import VENDORS

CENTER = {'certificate':'LG825678759', 'length_mm':15.66, 'width_mm':7.96, 'color':'E', 'clarity':'VVS1'}
RATIO_RANGE = (0.95, 1.05)  # Design preference for balanced, near-square heart outlines.
DEPTH_RANGE = (51.9, 61.0)
TABLE_RANGE = (58.0, 64.0)
COLORS = ('D','E','F')
CLARITIES = ('FL','IF','VVS1','VVS2','VS1')
FINISH = ('EXCELLENT','VERY GOOD')
TARGET_WIDTH = 5.4
TARGET_LENGTH = 5.4
WATCHLIST_IDS = {'0e9a5ad4-6912-407b-8da6-74346485ca76'}
AURELINNE_FEED = 'https://aurelinne.com/apps/diamond-proxy/api/v2/feed'
MIKADO_PRODUCTS = 'https://mikadodiamonds.com/products.json'
STIENHARDT_FEED = 'https://pxixbvvukwwmhmbyzdfu.supabase.co/functions/v1/storefront-api/search'
HEART_FIELDS = ['retailer','inventory_id','certificate','shape','carat','color','clarity','length_mm',
                'width_mm','depth_mm','ratio','table_pct','depth_pct','polish','symmetry','price_usd',
                'currency','availability','product_url','certificate_url','image_url','video_url','observed_at']


def number(value):
    try: return float(str(value).replace('%','').replace('$','').replace(',',''))
    except (TypeError, ValueError): return None


def normalize(row):
    result = dict(row)
    for key in ('carat','length_mm','width_mm','depth_mm','ratio','table_pct','depth_pct','price_usd'):
        result[key] = number(result.get(key))
    if not result.get('ratio') and result.get('length_mm') and result.get('width_mm'):
        result['ratio'] = result['length_mm'] / result['width_mm']
    return result


def apply_verified_overrides(rows):
    path=CONFIG/'heart_verified_overrides.json'
    overrides=read_json(path) if path.exists() else []
    by_id={(item.get('retailer'),str(item.get('inventory_id'))):item for item in overrides}
    enriched=[]
    for row in rows:
        result=dict(row); override=by_id.get((row.get('retailer'),str(row.get('inventory_id'))))
        if override:
            for key,value in override.items():
                if key not in ('retailer','inventory_id','source_note') and value not in (None,''):
                    result[key]=value
            result['verification_note']=override.get('source_note','')
        enriched.append(result)
    return enriched


def screen(row):
    r = normalize(row); failures=[]; warnings=[]
    if 'HEART' not in str(r.get('shape') or '').upper(): failures.append('shape is not Heart Brilliant')
    if str(r.get('color') or '').upper() not in COLORS: failures.append('color outside D-F')
    if str(r.get('clarity') or '').upper().replace(' ','') not in CLARITIES: failures.append('clarity below VS1')
    for field in ('polish','symmetry'):
        grade=str(r.get(field) or '').upper()
        if not grade: warnings.append(f'missing {field}')
        elif grade not in FINISH: warnings.append(f'{field} {grade.title()} below preferred Very Good')
    for field, bounds in (('ratio',RATIO_RANGE),('depth_pct',DEPTH_RANGE),('table_pct',TABLE_RANGE)):
        value=r.get(field)
        if value is None: warnings.append(f'missing {field}')
        elif not bounds[0] <= value <= bounds[1]: warnings.append(f'{field} {value:g} outside IGI Excellent candidate range {bounds[0]:g}-{bounds[1]:g}')
    if not r.get('certificate'): warnings.append('missing grading report')
    if not r.get('video_url'): warnings.append('missing stone-specific video')
    warnings.append('manual outline, cleft, lobes, point, and bow-tie review required')
    fit = None
    if r.get('length_mm') and r.get('width_mm'):
        penalty=((r['width_mm']-TARGET_WIDTH)/.35)**2+((r['length_mm']-TARGET_LENGTH)/.35)**2
        fit=max(0,100-8*penalty)
    return r, failures, warnings, round(fit,1) if fit is not None else None


def aurelinne_payload(offset, limit=20):
    """Broad query: apply quality preferences locally so borderline stones stay visible."""
    return {'offset':offset, 'limit':limit,
            'query':{'labgrown':True, 'shapes':['HEART'], 'sizes':{'from':0.25,'to':1.25}},
            'sort':{'field':'price','direction':'asc'}}


def collect_aurelinne(pages=40, delay=.1, session=None):
    session=session or requests.Session(); records=[]
    for page in range(pages):
        response=session.post(AURELINNE_FEED,json=aurelinne_payload(page*20),timeout=30)
        response.raise_for_status(); batch=extract_aurelinne(response.json())
        records.extend(batch)
        if len(batch)<20: break
        if delay: time.sleep(delay)
    write_json(RAW/'aurelinne'/'heart_side_stones.json',records)
    observed=datetime.now(timezone.utc).isoformat(timespec='seconds'); rows=[]
    for item in parse_aurelinne(records):
        inventory_id=item.get('id','')
        rows.append({'retailer':'Aurelinne','inventory_id':inventory_id,
            'certificate':item.get('certificate_number',''),'shape':item.get('shape',''),
            'carat':item.get('carat',''),'color':item.get('color',''),'clarity':item.get('clarity',''),
            'length_mm':item.get('length_mm',''),'width_mm':item.get('width_mm',''),
            'depth_mm':item.get('height_mm',''),'ratio':item.get('lw_ratio',''),
            'table_pct':item.get('table_pct',''),'depth_pct':item.get('depth_pct',''),
            'polish':item.get('polish',''),'symmetry':item.get('symmetry',''),
            'price_usd':item.get('price',''),'currency':'USD','availability':'listed',
            'product_url':f'https://aurelinne.com/pages/lab-grown?id={inventory_id}&stoneType=diamond',
            'certificate_url':'','image_url':item.get('image_url',''),'video_url':item.get('video_url',''),
            'observed_at':observed})
    rows=list({row['inventory_id']:row for row in rows if row['inventory_id']}.values())
    write_csv(CURRENT/'heart_side_stones.csv',rows,HEART_FIELDS)
    return rows


def _heart_row(retailer, inventory_id, source, observed):
    url=source.get('url') or source.get('product_url') or ''
    return {'retailer':retailer,'inventory_id':str(inventory_id or ''),
        'certificate':source.get('certificate') or source.get('certificate_number') or '',
        'shape':'Heart','carat':source.get('carat',''),'color':source.get('color',''),
        'clarity':source.get('clarity',''),'length_mm':source.get('length_mm',''),
        'width_mm':source.get('width_mm',''),'depth_mm':source.get('depth_mm') or source.get('height_mm',''),
        'ratio':source.get('ratio') or source.get('lw_ratio',''),'table_pct':source.get('table_pct',''),
        'depth_pct':source.get('depth_pct',''),'polish':source.get('polish',''),
        'symmetry':source.get('symmetry',''),'price_usd':source.get('price_usd') or source.get('price',''),
        'currency':'USD','availability':'listed','product_url':url,'certificate_url':'',
        'image_url':source.get('image_url',''),'video_url':source.get('video_url') or source.get('video_360_url',''),
        'observed_at':observed}


def collect_mikado(pages=10, delay=.1, session=None):
    session=session or requests.Session(); observed=datetime.now(timezone.utc).isoformat(timespec='seconds')
    raw=[]; rows=[]
    for page in range(1,pages+1):
        response=session.get(MIKADO_PRODUCTS,params={'limit':250,'page':page},timeout=35,
                             headers={'User-Agent':'Mozilla/5.0 DiamondFinder/17'})
        response.raise_for_status(); products=response.json().get('products',[]); raw.extend(products)
        hearts=[product for product in products if 'heart' in (' '.join(str(product.get(k) or '') for k in ('title','body_html','tags'))).lower()]
        for item in parse_mikado({'products':hearts}):
            rows.append(_heart_row('Mikado Diamonds',item.get('id'),item,observed))
        if len(products)<250: break
        if delay: time.sleep(delay)
    write_json(RAW/'mikado'/'heart_side_stones.json',raw)
    return list({(row['retailer'],row['inventory_id']):row for row in rows}.values())


def check_stienhardt(session=None):
    session=session or requests.Session()
    payload={'type':'LabGrown','diamondtype':'Heart','diamondcolor':'D,E,F',
             'diamondclarity':'IF,VVS1,VVS2,VS1','caratfrom':.25,'caratto':1.25,
             'sortby':'Recommended-ASC'}
    headers={'Accept':'application/json','Content-Type':'application/json','Origin':'https://stienhardt.com',
             'Referer':'https://stienhardt.com/','User-Agent':'Mozilla/5.0 DiamondFinder/17'}
    response=session.post(STIENHARDT_FEED,params={'page':1},json=payload,headers=headers,timeout=30)
    response.raise_for_status(); data=response.json(); write_json(RAW/'stienhardt'/'heart_page_1.json',data)
    return len((data.get('Diamonds') or {}).get('data') or [])


def collect_all_vendors(pages=40, delay=.1):
    rows=[]; coverage=[]; checked=datetime.now(timezone.utc).isoformat(timespec='seconds')
    collectors={'Aurelinne':lambda:collect_aurelinne(pages,delay),
                'Mikado Diamonds':lambda:collect_mikado(max(1,min(pages,10)),delay)}
    for vendor in VENDORS:
        if vendor.name in collectors:
            try:
                found=collectors[vendor.name](); rows.extend(found)
                coverage.append({'retailer':vendor.name,'status':'searched','records':len(found),'checked_at':checked,'notes':'Heart inventory collector completed'})
            except requests.RequestException as exc:
                coverage.append({'retailer':vendor.name,'status':'error','records':0,'checked_at':checked,'notes':type(exc).__name__})
        elif vendor.name=='Stienhardt':
            try:
                count=check_stienhardt(); coverage.append({'retailer':vendor.name,'status':'searched','records':count,'checked_at':checked,'notes':'Public Heart inventory query completed; parser pending if results appear'})
            except requests.RequestException as exc:
                coverage.append({'retailer':vendor.name,'status':'error','records':0,'checked_at':checked,'notes':type(exc).__name__})
        else:
            coverage.append({'retailer':vendor.name,'status':'not_searched','records':0,'checked_at':'','notes':'No validated heart-inventory connector'})
    rows=list({(row['retailer'],row['inventory_id']):row for row in rows}.values())
    write_csv(CURRENT/'heart_side_stones.csv',rows,HEART_FIELDS)
    write_csv(REPORTS/'heart_vendor_coverage.csv',coverage)
    write_json(REPORTS/'heart_vendor_coverage.json',coverage)
    return rows,coverage


def pair_score(a, b):
    a, af, aw, ascore=screen(a); b, bf, bw, bscore=screen(b)
    if af or bf: return None
    required=('length_mm','width_mm','carat')
    if any(a.get(k) is None or b.get(k) is None for k in required): return None
    deltas={'length_mm':abs(a['length_mm']-b['length_mm']),
            'width_mm':abs(a['width_mm']-b['width_mm']),
            'carat':abs(a['carat']-b['carat'])}
    # Side stones must first qualify as a near-identical pair. Scoring only orders pairs
    # after these gates; it must never compensate for a visible size or grade mismatch.
    if deltas['length_mm'] > .05 or deltas['width_mm'] > .05:
        return None
    if a.get('color') != b.get('color') or a.get('clarity') != b.get('clarity'):
        return None
    if a.get('ratio') is not None and b.get('ratio') is not None and abs(a['ratio']-b['ratio']) > .01:
        return None
    mismatch = deltas['length_mm']/.05 + deltas['width_mm']/.05
    mismatch += min(deltas['carat']/.05,2)*.35
    pair_warnings=[]
    if deltas['carat'] > .03:
        pair_warnings.append(f'carat difference {deltas["carat"]:.2f} ct; face-up dimensions still match')
    for field, tolerance in (('table_pct',2.0),('depth_pct',1.5)):
        if a.get(field) is not None and b.get(field) is not None:
            delta=abs(a[field]-b[field])
            mismatch += min(delta/tolerance,2)*.3
            if delta > tolerance: pair_warnings.append(f'{field} difference {delta:g} exceeds preference')
    if a.get('polish') != b.get('polish') or a.get('symmetry') != b.get('symmetry'):
        mismatch += .5
    individual=(ascore+bscore)/2 if ascore is not None and bscore is not None else 0
    evidence=sum((8 if not x.get('certificate') else 0)+(3 if not x.get('video_url') else 0) for x in (a,b))
    total=max(0, individual-mismatch*3-evidence)
    return {'pair_score':round(total,1),'size_fit_score':round(individual,1),'match_penalty':round(mismatch,2),
            'left':a,'right':b,'warnings':sorted(set(aw+bw+pair_warnings))}


def rank_pairs(rows):
    # Screen the complete inventory before pairing. Do not pre-truncate by individual
    # size score: two slightly less ideal stones can form the best-matched pair.
    candidates=[]
    for row in rows:
        normalized,failures,_,_=screen(row)
        if not failures and all(normalized.get(key) is not None for key in ('length_mm','width_mm','carat')):
            candidates.append(normalized)
    pairs=[]
    for a,b in itertools.combinations(candidates,2):
        result=pair_score(a,b)
        if result: pairs.append(result)
    pairs.sort(key=lambda x:x['pair_score'], reverse=True)
    for rank,pair in enumerate(pairs,1): pair['rank']=rank
    return pairs


def heart_path(cx, cy, width, length, rotation=0):
    # Symmetric face-up outline; dimensions are exact, facet appearance is illustrative.
    pts=[]
    for i in range(181):
        t=2*math.pi*i/180
        x=16*math.sin(t)**3; y=13*math.cos(t)-5*math.cos(2*t)-2*math.cos(3*t)-math.cos(4*t)
        pts.append((x/32*width, -y/29*length))
    rad=math.radians(rotation); transformed=[]
    for x,y in pts:
        transformed.append((cx+x*math.cos(rad)-y*math.sin(rad),cy+x*math.sin(rad)+y*math.cos(rad)))
    return 'M '+' L '.join(f'{x:.3f},{y:.3f}' for x,y in transformed)+' Z'


def center_path(cx,cy,width,length):
    # Six-sided Dutch-marquise outline, not a facet-performance simulation.
    return f'M {cx:.3f},{cy-length/2:.3f} L {cx+width/2:.3f},{cy-length*.18:.3f} L {cx+width/2:.3f},{cy+length*.18:.3f} L {cx:.3f},{cy+length/2:.3f} L {cx-width/2:.3f},{cy+length*.18:.3f} L {cx-width/2:.3f},{cy-length*.18:.3f} Z'


def scale_svg(heart_width, orientation='outward'):
    heart_length=heart_width*.90; gap=.15
    center_w,center_l=CENTER['width_mm'],CENTER['length_mm']
    rotation=0 if orientation=='upright' else 90
    lateral=heart_width if orientation=='upright' else heart_length
    total=center_w+2*lateral+4*gap; height=max(center_l,heart_width if rotation else heart_length)+4
    cx=total/2; cy=height/2
    leftx=cx-center_w/2-gap-lateral/2; rightx=cx+center_w/2+gap+lateral/2
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total:.2f}mm" height="{height:.2f}mm" viewBox="0 0 {total:.3f} {height:.3f}" data-center-length-mm="{center_l:.3f}" data-center-width-mm="{center_w:.3f}" role="img" aria-label="Scale rendering in millimeters">
    <rect width="100%" height="100%" fill="#faf8f2"/><g fill="#eaf4f7" stroke="#244f43" stroke-width=".08">
    <path d="{center_path(cx,cy,center_w,center_l)}"/><path d="{heart_path(leftx,cy,heart_width,heart_length,rotation)}"/><path d="{heart_path(rightx,cy,heart_width,heart_length,-rotation)}"/></g>
    <g stroke="#aa7a2e" stroke-width=".04" opacity=".65"><path d="M0,{height-1} H{total}"/>{''.join(f'<path d="M{x},{height-1} v.35"/>' for x in range(math.ceil(total)+1))}</g>
    <g font-family="sans-serif" font-size=".65" fill="#17201d"><text x=".4" y=".8">True-scale plan view · dimensions in mm</text><text x=".4" y="{height-.25}">{heart_width:.1f} mm hearts · points face west/east · {gap:.2f} mm clearance · total span {total-4*gap:.1f} mm</text></g></svg>'''


def report_html(pairs, rows=None, coverage=None):
    rows=rows or []
    coverage=coverage or []
    screened_count=sum(not screen(row)[1] for row in rows)
    variants=[('subtle',4.4),('balanced',5.0),('bold',5.6)]
    renders=''.join(f'<section><h3>{name.title()} · {size:.1f} mm wide each</h3><p>Left point faces west; right point faces east. Rounded lobes face inward toward the center.</p>{scale_svg(size,"outward")}</section>' for name,size in variants)
    pair_rows=''.join(f'<tr><td>{p["rank"]}</td><td>{p["pair_score"]}</td><td>{p["left"].get("certificate","") or "Missing"}</td><td>{p["right"].get("certificate","") or "Missing"}</td><td>{p["left"].get("width_mm","")} × {p["left"].get("length_mm","")}</td><td>{p["right"].get("width_mm","")} × {p["right"].get("length_mm","")}</td></tr>' for p in pairs[:20]) or '<tr><td colspan="6">No eligible matched pair yet. This does not mean the market was fully searched.</td></tr>'
    candidates=[]
    for raw in rows:
        r,failures,warnings,fit=screen(raw)
        status='Excluded' if failures else ('Review' if warnings else 'Preferred')
        url=html.escape(str(r.get('product_url') or ''))
        link=f'<a href="{url}">View</a>' if url else ''
        message=html.escape('; '.join(failures+warnings))
        candidates.append((fit if fit is not None else -1,
            f'<tr><td>{status}</td><td>{html.escape(str(r.get("retailer") or ""))}</td><td>{r.get("carat") or ""}</td><td>{html.escape(str(r.get("color") or ""))}/{html.escape(str(r.get("clarity") or ""))}</td><td>{r.get("length_mm") or ""} × {r.get("width_mm") or ""}</td><td>{r.get("ratio") or ""}</td><td>${r.get("price_usd") or ""}</td><td>{html.escape(str(r.get("certificate") or "Missing"))}</td><td>{message}</td><td>{link}</td></tr>'))
    candidates.sort(key=lambda value:value[0],reverse=True)
    featured=[value for value in candidates if any(watch_id in value[1] for watch_id in WATCHLIST_IDS)]
    display=featured+[value for value in candidates if value not in featured][:100]
    candidate_rows=''.join(value[1] for value in display) or '<tr><td colspan="10">Inventory has not been collected. Run <code>py heart_side_stones.py --collect-all</code>.</td></tr>'
    coverage_rows=''.join(f'<tr><td>{html.escape(str(item.get("retailer","")))}</td><td>{html.escape(str(item.get("status","")))}</td><td>{item.get("records",0)}</td><td>{html.escape(str(item.get("checked_at","") or "—"))}</td><td>{html.escape(str(item.get("notes","")))}</td></tr>' for item in coverage) or '<tr><td colspan="5">No multi-vendor coverage run recorded.</td></tr>'
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Heart Side-Stone Finder</title><style>body{{margin:auto;max-width:1200px;padding:35px;font:15px/1.5 system-ui;color:#17201d;background:#f5f2eb}}h1,h2{{font-family:Georgia,serif}}section,.card{{background:white;border:1px solid #dcd7cc;border-radius:14px;padding:18px;margin:14px 0}}svg{{display:block;max-width:100%;height:auto;margin:12px auto;border:1px solid #ddd}}table{{width:100%;border-collapse:collapse;background:white}}th,td{{padding:9px;border:1px solid #ddd;text-align:left}}.note{{background:#fff0ce;padding:12px;border-radius:9px}}</style></head><body><h1>Heart Side-Stone Finder</h1><p>Independent companion module for center diamond {CENTER['certificate']} ({CENTER['length_mm']} × {CENTER['width_mm']} mm). Heart criteria never affect the Dutch-marquise ranking.</p>
    <div class="card"><h2>Screening baseline</h2><ul><li>Design-preferred near-square outline: L/W {RATIO_RANGE[0]}–{RATIO_RANGE[1]}. This is an aesthetic target, not a universal laboratory cut grade. Screening preferences: depth {DEPTH_RANGE[0]}–{DEPTH_RANGE[1]}%, table {TABLE_RANGE[0]}–{TABLE_RANGE[1]}%.</li><li>D–F color and VS1 or better allow slight flexibility around the E/VVS1 center. Each side stone must still have the same color and clarity as its partner.</li><li>Hard visible-match gates: ≤0.05 mm length and width difference and ≤0.01 ratio difference. Carat, table, and depth differences affect ranking and warnings but do not veto a face-up dimensional match.</li><li>Manual confirmation: matched outline, cleft depth, lobes, wings, point, facet pattern, brightness, and bow-tie behavior in synchronized videos.</li></ul><p class="note">Size recommendations are design scenarios derived from the center’s 7.96 mm face-up width—not a laboratory cut standard. Confirm spacing, tilt, prongs, finger coverage, and basket engineering with the ring designer.</p></div>
    <h2>True-scale plan renderings</h2><p>The hearts run west-to-east: points face away from the center and rounded lobes sit against its sides with 0.15 mm modeled clearance. Print at 100% with browser scaling disabled. Verify the millimeter ruler before using as a physical reference. Outlines are dimensionally scaled; facets, tilt, prongs, and perspective are illustrative.</p>{renders}
    <h2>Vendor coverage</h2><table><thead><tr><th>Retailer</th><th>Status</th><th>Records</th><th>Checked</th><th>Notes</th></tr></thead><tbody>{coverage_rows}</tbody></table>
    <h2>Collected candidates</h2><p>{len(rows)} heart listings were collected across supported retailers. Watchlisted examples appear first, followed by the 100 closest dimensional fits. “Missing” means the report identity still needs retrieval and validation.</p><table><thead><tr><th>Status</th><th>Retailer</th><th>Carat</th><th>Grade</th><th>Length × width</th><th>Ratio</th><th>Price</th><th>Report</th><th>Flags</th><th>Listing</th></tr></thead><tbody>{candidate_rows}</tbody></table>
    <h2>Matched inventory pairs</h2><p>Pipeline: {len(rows)} collected → {screened_count} individually eligible → {len(pairs)} highest-ranked compatible pairs shown. Compatibility gates are applied before pair ranking.</p><table><thead><tr><th>Rank</th><th>Pair score</th><th>Left IGI</th><th>Right IGI</th><th>Left mm</th><th>Right mm</th></tr></thead><tbody>{pair_rows}</tbody></table></body></html>'''


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--input',default='heart_side_stones.csv')
    parser.add_argument('--collect-aurelinne',action='store_true',help='Collect broad live Aurélinne heart inventory before ranking')
    parser.add_argument('--collect-all',action='store_true',help='Run every validated heart-inventory connector and record coverage')
    parser.add_argument('--pages',type=int,default=40,help='Maximum 20-result Aurélinne pages to collect')
    parser.add_argument('--delay',type=float,default=.1,help='Delay between inventory requests')
    args=parser.parse_args(); ensure_layout()
    coverage=[]
    if args.collect_all: rows,coverage=collect_all_vendors(args.pages,args.delay)
    elif args.collect_aurelinne: rows=collect_aurelinne(args.pages,args.delay)
    else:
        rows=read_csv(CURRENT/args.input)
        coverage=read_json(REPORTS/'heart_vendor_coverage.json') if (REPORTS/'heart_vendor_coverage.json').exists() else []
    rows=apply_verified_overrides(rows)
    write_csv(CURRENT/'heart_side_stones.csv',rows,HEART_FIELDS)
    all_pairs=rank_pairs(rows); pairs=all_pairs[:100]
    flattened=[{'rank':p['rank'],'pair_score':p['pair_score'],'size_fit_score':p['size_fit_score'],'match_penalty':p['match_penalty'],
                'left_certificate':p['left'].get('certificate',''),'right_certificate':p['right'].get('certificate',''),
                'left_retailer':p['left'].get('retailer',''),'right_retailer':p['right'].get('retailer',''),
                'left_price':p['left'].get('price_usd',''),'right_price':p['right'].get('price_usd',''),
                'warnings':'; '.join(p['warnings'])} for p in pairs]
    pair_fields=['rank','pair_score','size_fit_score','match_penalty','left_certificate','right_certificate',
                 'left_retailer','right_retailer','left_price','right_price','warnings']
    write_csv(REPORTS/'heart_side_stone_pairs.csv',flattened,pair_fields)
    write_json(REPORTS/'heart_side_stone_pairs.json',pairs)
    (REPORTS/'heart_side_stone_report.html').write_text(report_html(pairs,rows,coverage),encoding='utf-8')
    for name,size in (('subtle',4.4),('balanced',5.0),('bold',5.6)):
        (REPORTS/f'heart_layout_{name}.svg').write_text(scale_svg(size,'outward'),encoding='utf-8')
    print(f'Heart Side-Stone Finder: {len(rows)} stones, {len(all_pairs)} compatible pairs; top {len(pairs)} written')


if __name__=='__main__': main()
