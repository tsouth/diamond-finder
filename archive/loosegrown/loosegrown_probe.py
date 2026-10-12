"""Loose Grown Diamond Dutch search via public WordPress JSON endpoint.
Run: py loosegrown_probe.py --pages 10
Offline parser test: py loosegrown_probe.py --response saved.json
If site requires a session, capture the JSON response rather than sharing cookies.
"""
import argparse,csv,json,re,time,html
from pathlib import Path
from urllib.parse import urljoin
import requests
BASE='https://www.loosegrowndiamond.com'
ENDPOINT=BASE+'/wp-json/custom/v1/get-products'
FIELDS=['retailer','id','title','shape','carat','color','clarity','length_mm','width_mm','ratio','depth_pct','table_pct','polish','symmetry','price_usd','certificate','url','image_url','video_url','shape_verified']
HEADERS={'Accept':'application/json, */*','User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154.0.0.0 Safari/537.36','Referer':BASE+'/?s=dutch&post_type=product'}
def get(obj,*names):
    for n in names:
        if isinstance(obj,dict):
            for k,v in obj.items():
                if k.lower().replace('_','').replace('-','')==n.lower().replace('_','').replace('-','') and v not in ('',None):return v
    return ''
def num(v):
    if isinstance(v,(int,float)):return float(v)
    match=re.search(r'\d+(?:[.,]\d+)?',str(v or '').replace(',',''))
    return float(match.group()) if match else ''
def clean(v):
    if isinstance(v,dict):return clean(get(v,'rendered','value','url','src'))
    return html.unescape(re.sub('<[^>]+>',' ',str(v or ''))).strip()
def product_list(payload):
    if isinstance(payload,list):return payload
    if isinstance(payload,dict):
        for key in ('products','data','results','items','posts'):
            val=payload.get(key)
            if isinstance(val,list):return val
            if isinstance(val,dict):
                nested=product_list(val)
                if nested:return nested
        if any(k in payload for k in ('id','ID','product_id','title','name')):return [payload]
    return []
def parse(payload):
    rows=[]
    colors={'10':'D','9':'E','8':'F','7':'G','6':'H'}
    clarities={'9':'VVS1','8':'VVS2','7':'VS1'}
    for obj in product_list(payload):
        if not isinstance(obj,dict):continue
        a=obj.get('aj_diamond') or {}
        title=clean(obj.get('title'))
        shape=clean(a.get('shape_title') or a.get('shape') or obj.get('shape'))
        carat=num(a.get('carat') or obj.get('carat'))
        if not carat:
            m=re.search(r'(\d+(?:\.\d+)?)\s*(?:ct|carat)',title,re.I)
            carat=float(m.group(1)) if m else ''
        length=num(a.get('length'));width=num(a.get('width'))
        if not length or not width:
            m=re.search(r'(\d+(?:\.\d+)?)\s*[-x×]\s*(\d+(?:\.\d+)?)\s*[x×]',str(a.get('mm') or ''))
            if m:length,width=map(float,m.groups())
        color=re.search(r'\b([D-M])\s+Color\b',title,re.I)
        clarity=re.search(r'\b(FL|IF|VVS1|VVS2|VS1|VS2|SI1)\s+Clarity\b',title,re.I)
        color=color.group(1).upper() if color else colors.get(str(a.get('color')),'')
        clarity=clarity.group(1).upper() if clarity else clarities.get(str(a.get('clarity')),'')
        cert=clean(a.get('certificate') or '')
        report=re.search(r'[?&]r=(?:LG)?(\d+)',cert)
        cert=report.group(1) if report else ''
        label='LABELED DUTCH - verify facet style' if 'dutch' in shape.lower() else 'UNVERIFIED - inspect'
        if 'HEXAGONAL MODIFIED STEP CUT' in title.upper():label='EXCLUDE - Hexagonal Modified Step Cut'
        rows.append(dict(retailer='Loose Grown Diamond',id=clean(obj.get('sku') or a.get('sku') or obj.get('id')),title=title,shape=shape or 'Other (unverified)',carat=carat,color=color,clarity=clarity,length_mm=length,width_mm=width,ratio=round(length/width,3) if length and width else '',depth_pct=num(a.get('depth')),table_pct=num(a.get('av_table')),polish={'3':'Excellent','2':'Very Good'}.get(str(a.get('polish')),''),symmetry={'3':'Excellent','2':'Very Good'}.get(str(a.get('symmetry')),''),price_usd=num(obj.get('price')),certificate=cert,url=clean(obj.get('link')),image_url=clean(a.get('image')),video_url=clean(a.get('video')),shape_verified=label))
    return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pages',type=int,default=10);ap.add_argument('--per-page',type=int,default=21);ap.add_argument('--delay',type=float,default=1.5);ap.add_argument('--response');ap.add_argument('--import-dir',default='loosegrown_responses');a=ap.parse_args()
    rows=[];seen=set();rawdir=Path('loosegrown_responses');rawdir.mkdir(exist_ok=True)
    if a.response or list(Path(a.import_dir).glob('page_*.json')):
        paths=[Path(a.response)] if a.response else sorted(Path(a.import_dir).glob('page_*.json'),key=lambda p:int(re.search(r'page_(\d+)',p.name).group(1)))
        for path in paths:
            data=json.loads(path.read_text(encoding='utf-8-sig'))
            found=parse(data);rows.extend(found)
            print('Offline imported:',path,len(found),'rows')
        if not a.response:
            print('Saved JSON mode: skipped Sucuri-blocked live endpoint.')
    else:
        session=requests.Session()
        for page in range(1,a.pages+1):
            params={'orderby':'price','order':'asc','page':page,'per_page':a.per_page,'search':'dutch','price_range':'0,50000'}
            try:
                response=session.get(ENDPOINT,params=params,headers=HEADERS,timeout=40,allow_redirects=True)
                print('Loose Grown Diamond page',page,'HTTP',response.status_code,'bytes',len(response.content),'final URL:',response.url,'content-type:',response.headers.get('content-type'))
                (rawdir/f'page_{page}_response.txt').write_text(response.text,encoding='utf-8')
                if 'json' not in response.headers.get('content-type','').lower():
                    print('WARNING: LGD returned non-JSON, likely a redirect, security challenge, or HTML page. Saved response to',rawdir/f'page_{page}_response.txt')
                    print('  Redirect history:',[(h.status_code,h.headers.get('Location','')) for h in response.history])
                    break
                response.raise_for_status()
                data=response.json()
                (rawdir/f'page_{page}.json').write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
                found=parse(data)
            except (requests.RequestException,ValueError) as exc:
                print('WARNING: LGD request/JSON failure:',exc);break
            print('  parsed',len(found),'records')
            new=[r for r in found if r['id'] not in seen]
            if not new:
                print('  No new records; stopping pagination');break
            rows.extend(new);seen.update(r['id'] for r in new)
            if len(found)<a.per_page:
                print('  Short page; stopping pagination');break
            if page<a.pages:time.sleep(a.delay)
    unique={r['id']:r for r in rows};rows=list(unique.values())
    with open('loosegrown_diamonds.csv','w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    print('Wrote',len(rows),'Loose Grown Diamond records')
    if rows:print('Sample:',json.dumps(rows[:2],indent=2))
    else:print('WARNING: zero rows means unavailable/unparsed, NOT confirmed zero inventory.')
if __name__=='__main__':main()
