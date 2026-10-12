"""Inspect Stienhardt storefront response, then export confidently identified diamonds.
Usage: py stienhardt_probe.py --pages 3
Requires: py -m pip install requests
Credential: set STIENHARDT_BASIC_AUTH environment variable to your own authorized Basic header value, if required.
"""
import argparse, csv, json, os, re, sys, time
from pathlib import Path
import requests
from storage import CURRENT, RAW, ensure_layout

URL='https://pxixbvvukwwmhmbyzdfu.supabase.co/functions/v1/storefront-api/search'
PAYLOAD={'type':'LabGrown','diamondtype':'Dutch Marquise','diamondcolor':'D,E',
'diamondclarity':'VS1,IF,VVS1,VVS2','diamondcut':'Excellent','reportby':'',
'caratfrom':3,'caratto':5.2,'lwfrom':1.8,'lwto':2.12,'pricefrom':'','priceto':'',
'depthfrom':58,'depthto':67,'tablefrom':55,'tableto':65,'polish':'Excellent',
'symmetry':'Excellent','quickship':'0','featureddeal':'0','certnum':'',
'sortby':'Recommended-ASC'}
HEADERS={'Accept':'application/json','Content-Type':'application/json','Origin':'https://stienhardt.com','Referer':'https://stienhardt.com/','User-Agent':'Mozilla/5.0 DiamondComparison/1.0'}
FIELDS=['sku','carat','length_mm','width_mm','depth_mm','ratio','color','clarity','cut','polish','symmetry','depth_pct','table_pct','price_usd','lab','certificate','image_url','video_360_url','product_url','availability','score']

def num(x):
    if x is None or isinstance(x,bool):return None
    try:return float(re.sub(r'[^0-9.\-]','',str(x)))
    except ValueError:return None

def pick(d,*keys):
    for k in keys:
        if k in d and d[k] not in (None,''):return d[k]
    return None

def extract(node, path='root'):
    if isinstance(node,list):
        for i,v in enumerate(node):yield from extract(v,f'{path}[{i}]')
    elif isinstance(node,dict):
        # Detect plausible loose diamond records, not pagination and filter metadata.
        keys={str(k).lower() for k in node}
        if keys.intersection({'carat','caratweight','carat_weight','weight','measurements','measurement','dimensions','certnum','certificatenumber','certificate_number'}):
            yield path,node
        for k,v in node.items():
            if isinstance(v,(dict,list)):yield from extract(v,f'{path}.{k}')

def normalize(d):
    if d.get('shape') != 'Dutch Marquise' or 'sku' not in d:
        return None
    dims=d.get('measurement','')
    m=re.search(r'(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)',dims)
    if not m:return None
    length,width,height=map(float,m.groups())
    shopify=(d.get('shopify_res') or {}).get('product') or {}
    handle=shopify.get('handle')
    return dict(sku=d['sku'],carat=d.get('carat'),length_mm=length,width_mm=width,depth_mm=height,
        ratio=round(length/width,3),color=d.get('color'),clarity=d.get('clarity'),
        cut=d.get('cut'),polish=d.get('polish'),symmetry=d.get('symmetry'),
        depth_pct=d.get('depth'),table_pct=d.get('table'),price_usd=d.get('original_price'),
        lab=d.get('lab'),certificate=d.get('cert_num'),image_url=d.get('cover_pic'),
        video_360_url=d.get('workshop_preview_url'),
        product_url='https://stienhardt.com/products/'+handle if handle else '',
        availability=d.get('upstream_status'),
        score=round(((length-15.5)/.35)**2+((width-7.8)/.2)**2,3))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--pages',type=int,default=5)
    ap.add_argument('--output',default=str(CURRENT/'diamonds_enriched.csv'))
    ap.add_argument('--offline',action='store_true',help='Parse existing stienhardt_page_*.json without network')
    args=ap.parse_args()
    ensure_layout(); rawdir=RAW/'stienhardt';rawdir.mkdir(parents=True,exist_ok=True)
    auth=os.getenv('STIENHARDT_BASIC_AUTH','').strip()
    if auth:HEADERS['Authorization']=auth if auth.lower().startswith('basic ') else 'Basic '+auth
    session=requests.Session();out=[];seen=set()
    for page in range(1,args.pages+1):
        filename=rawdir/f'page_{page}.json'
        if args.offline:
            if not filename.exists():print(f'Missing {filename}; stopping.');break
            obj=json.loads(filename.read_text(encoding='utf-8'))
        else:
            try:
                r=session.post(URL,params={'page':page},json=PAYLOAD,headers=HEADERS,timeout=30)
                print(f'Page {page}: HTTP {r.status_code}')
                r.raise_for_status();obj=r.json()
            except (requests.RequestException,ValueError) as e:
                print('Request/JSON error:',str(e)[:500]);break
            filename.write_text(json.dumps(obj,indent=2),encoding='utf-8')
        container=obj.get('Diamonds',{})
        records=container.get('data',[])
        print(f'Page {page}: {len(records)} diamonds; last_page={container.get("last_page")}')
        for d in records:
            x=normalize(d)
            if x and x['sku'] not in seen:seen.add(x['sku']);out.append(x)
        if page >= container.get('last_page',page) or not records:break
        if not args.offline:time.sleep(.5)
    out.sort(key=lambda x:x['score'])
    with open(args.output,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(out)
    print(f'Exported {len(out)} diamonds to {args.output}')
if __name__=='__main__':main()
