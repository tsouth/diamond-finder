"""Mikado Diamonds Shopify collection importer (public products.json).
Run: py mikado_probe.py --pages 10
Offline test: py mikado_probe.py --response mikado_responses/page_1.json
The collection's VVS1 label does not guarantee every item is a Dutch marquise.
"""
import argparse,csv,html,json,re,time
from pathlib import Path
from urllib.parse import urljoin
import requests
from storage import CURRENT, RAW, ensure_layout
from identity import extract_report, extract_supplier_id
BASE='https://mikadodiamonds.com'
COLLECTION='dutch-marquise-vvs1-lab-grown-diamonds'
FIELDS=['retailer','id','title','shape','carat','color','clarity','length_mm','width_mm','ratio','depth_pct','table_pct','polish','symmetry','price_usd','certificate','supplier_stock_id','url','image_url','video_url','shape_verified']
HEADERS={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36','Accept':'application/json, */*'}
def clean(s):return html.unescape(re.sub(r'<[^>]*>',' ',str(s or ''))).strip()
def number(v):
    m=re.search(r'\d+(?:\.\d+)?',str(v or '').replace(',',''))
    return float(m.group()) if m else ''
def extract(pattern,text):
    m=re.search(pattern,text,re.I)
    return m.group(1).strip() if m else ''
def parse(payload):
    products=payload.get('products',[]) if isinstance(payload,dict) else payload if isinstance(payload,list) else []
    rows=[]
    for p in products:
        if not isinstance(p,dict):continue
        title=clean(p.get('title')); body=clean(p.get('body_html')); text=title+' '+body
        tags=clean(p.get('tags')); combined=text+' '+tags
        carat=number(extract(r'(\d+(?:\.\d+)?)\s*(?:ct|carat)\b',text))
        color=extract(r'\bcolou?r\s*[:\-]\s*([D-M])\b',text)
        clarity=extract(r'\bclarity\s*[:\-]\s*(FL|IF|VVS1|VVS2|VS1|VS2|SI1)\b',text)
        if not color:color=extract(r'\b([D-M])\s*[/\-]\s*(?:VVS1|VVS2|VS1)\b',title)
        if not clarity:clarity=extract(r'\b(VVS1|VVS2|VS1|IF|FL)\b',title)
        dims=re.search(r'\bmeasurements?\s*[:\-]?\s*(\d{1,2}(?:\.\d+)?)\s*[-x×]\s*(\d{1,2}(?:\.\d+)?)\s*[x×]\s*(\d{1,2}(?:\.\d+)?)',text,re.I) or re.search(r'\b(\d{1,2}(?:\.\d+)?)\s*[x×]\s*(\d{1,2}(?:\.\d+)?)\s*[x×]\s*(\d{1,2}(?:\.\d+)?)\s*mm\b',text,re.I)
        length,width=(float(dims.group(1)),float(dims.group(2))) if dims else ('','')
        if length and width and length<width:length,width=width,length
        ratio=round(length/width,3) if length and width else ''
        depth=number(extract(r'\bdepth\s*[:\-]\s*(\d+(?:\.\d+)?)\s*%',text))
        table=number(extract(r'\btable\s*[:\-]\s*(\d+(?:\.\d+)?)\s*%',text))
        polish=extract(r'\bpolish\s*[:\-]\s*(excellent|very good|good|EX|VG)\b',text)
        symmetry=extract(r'\bsymmetry\s*[:\-]\s*(excellent|very good|good|EX|VG)\b',text)
        variants=p.get('variants') or []
        variant=next((v for v in variants if v.get('available')),variants[0] if variants else {})
        sku=str(variant.get('sku') or p.get('sku') or '')
        cert=extract_report(text, tags, sku, title)
        stock=extract_supplier_id(sku, tags, combined, title)
        if re.search(r'hexagonal\s+modified\s+step\s+cut',combined,re.I):
            shape='EXCLUDED - Hexagonal Modified Step Cut'; status='EXCLUDE - Hexagonal Modified Step Cut'
        elif re.search(r'hexagonal\s+modified\s+brilliant',combined,re.I):
            shape='Hexagonal Modified Brilliant'; status='LABELED BRILLIANT - inspect facets'
        elif re.search(r'dutch[\s-]*marquise',combined,re.I):
            shape='Dutch Marquise'; status='LABELED DUTCH - verify photo/report'
        elif re.search(r'hexagonal',combined,re.I):
            shape='Hexagonal (facet unverified)'; status='HEXAGONAL LABEL - inspect IGI facet style'
        else:
            shape='Other (unverified)'; status='UNVERIFIED - check shape'
        price=number(variant.get('price'))
        images=p.get('images') or []
        image=(p.get('image') or {}).get('src') or (images[0].get('src') if images else '')
        handle=p.get('handle','');url=BASE+'/products/'+handle if handle else ''
        if handle:url=BASE+'/collections/'+COLLECTION+'/products/'+handle
        rows.append(dict(retailer='Mikado Diamonds',id=str(p.get('id') or handle),title=title,shape=shape,carat=carat,color=color,clarity=clarity,length_mm=length,width_mm=width,ratio=ratio,depth_pct=depth,table_pct=table,polish=polish,symmetry=symmetry,price_usd=price,certificate=cert,supplier_stock_id=stock,url=url,image_url=image,video_url='',shape_verified=status))
    return rows
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pages',type=int,default=10);ap.add_argument('--limit',type=int,default=250);ap.add_argument('--delay',type=float,default=1.5);ap.add_argument('--response');a=ap.parse_args()
    ensure_layout();rows=[];seen=set();folder=RAW/'mikado';folder.mkdir(parents=True,exist_ok=True)
    if a.response:
        rows=parse(json.loads(Path(a.response).read_text(encoding='utf-8-sig')))
        print('Offline parsed:',len(rows))
    else:
        session=requests.Session()
        for page in range(1,a.pages+1):
            endpoint=f'{BASE}/collections/{COLLECTION}/products.json'
            try:
                response=session.get(endpoint,params={'page':page,'limit':a.limit},headers=HEADERS,timeout=35)
                print('Mikado page',page,'HTTP',response.status_code,'bytes',len(response.content),'type',response.headers.get('content-type'),'final',response.url)
                (folder/f'page_{page}.txt').write_text(response.text,encoding='utf-8')
                response.raise_for_status()
                payload=response.json()
                (folder/f'page_{page}.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
                found=parse(payload)
            except (requests.RequestException,ValueError) as exc:
                print('WARNING: Mikado fetch/JSON error:',exc,'(see saved page text if present)');break
            fresh=[r for r in found if r['id'] not in seen]
            rows.extend(fresh);seen.update(r['id'] for r in fresh)
            print('  products:',len(found),'new:',len(fresh))
            if not fresh or len(found)<a.limit:break
            if page<a.pages:time.sleep(a.delay)
    rows=list({r['id']:r for r in rows}.values())
    with (CURRENT/'mikado_diamonds.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    print('Wrote',len(rows),'Mikado records to',CURRENT/'mikado_diamonds.csv')
    if not rows:print('WARNING: zero rows is not proof of zero inventory. Inspect mikado_responses/page_1.txt.')
if __name__=='__main__':main()
