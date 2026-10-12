"""Calavera public diamond search RSC card extractor.
Run: py calavera_probe.py --pages 5
Or test captured response: py calavera_probe.py --response "calavera_response.txt"
Only listing-card fields are available; measurements/certificates need detail pages.
"""
import argparse,csv,json,re,time
from pathlib import Path
from urllib.parse import urlencode
import requests
from storage import CURRENT, RAW, ensure_layout
BASE='https://calaveranewyork.com'
FILTERS={'carats':'3.7,4.6','colors':'D,E','clarities':'FL,IF,VVS1,VVS2,VS1','shapes':'hexagonal,other'}
HEADERS={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154.0.0.0 Safari/537.36','Accept':'*/*','RSC':'1','Next-Url':'/en/diamonds/lab-grown','Referer':BASE+'/diamonds/lab-grown'}
PATTERN=re.compile(r'(?P<record>[0-9a-z]+):\["\$","\$L\w+",null,\{"ref":"\$undefined","href":"(?P<href>/diamonds/[^\"]+)"(?P<content>.*?)(?=\n[0-9a-z]+:|\Z)',re.S)
def parse(s):
    out=[]
    for m in PATTERN.finditer(s):
        blob=m.group('content'); href=m.group('href')
        title=re.search(r'"title":"([0-9.]+ct [^\"]+ Diamond)"',blob)
        price=re.search(r'"amount":([0-9.]+),"currencyCode":"USD"',blob)
        if not title or not price: continue
        name=title.group(1)
        slug=re.search(r'-colour-([a-z]+)-clarity-([a-z0-9]+)-(?:igi|gia|hrd)-',href)
        color=slug.group(1).upper() if slug else ''
        clarity=slug.group(2).upper() if slug else ''
        carat=re.match(r'([0-9.]+)ct',name)
        if not carat or not 3.7 <= float(carat.group(1)) <= 4.6: continue
        lower_name=name.lower()
        if 'square radiant' in lower_name:
            shape='Square Radiant'; shape_verified='EXCLUDE - square radiant'
        elif 'hexagonal' in lower_name:
            shape='Hexagonal'; shape_verified='HEXAGONAL LABEL - inspect IGI facet style'
        else:
            shape='Other'; shape_verified='REVIEW - other cut'
        out.append({'retailer':'Calavera','carat':float(carat.group(1)) if carat else '', 'title':name,'color':color, 'clarity':clarity, 'price_usd':float(price.group(1)),'url':BASE+href,'id':href.rsplit('-',5)[-1] if False else href[-36:],'dimensions':'','certificate':'','shape_verified':shape_verified, 'shape':shape})
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pages',type=int,default=1);ap.add_argument('--response',help='Local saved RSC response text');ap.add_argument('--delay',type=float,default=1.5);a=ap.parse_args()
    ensure_layout();rawdir=RAW/'calavera';rawdir.mkdir(parents=True,exist_ok=True);rows=[]
    if a.response:
        s=Path(a.response).read_text(encoding='utf-8'); rows=parse(s); print('Local response parsed:',len(rows))
    else:
        for page in range(1,a.pages+1):
            params=dict(FILTERS,page=page)
            r=requests.get(BASE+'/diamonds/lab-grown',params={**params,'_rsc':'wl07QX5LiIsbj4qY'},headers=HEADERS,timeout=35)
            print('Page',page,'HTTP',r.status_code,'bytes',len(r.content),'content-type',r.headers.get('Content-Type'))
            r.raise_for_status()
            (rawdir/f'page_{page}.txt').write_text(r.text,encoding='utf-8')
            found=parse(r.text);print('  Listing cards:',len(found));rows+=found
            if not found: print('  No RSC listing cards parsed; inspect saved page for changed markup or missing Next-Router-State-Tree.');break
            if page > 1 and not any(r['id'] not in {x['id'] for x in rows[:-len(found)]} for r in found):
                print('  Repeated page detected; stopping pagination.');break
            time.sleep(a.delay)
    unique={r['id']:r for r in rows};rows=list(unique.values())
    rows.sort(key=lambda x:(abs(x['carat']-4.0),x['price_usd']))
    with (CURRENT/'calavera_diamonds.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['retailer','carat','title','color','clarity','price_usd','url','id','dimensions','certificate','shape_verified','shape']);w.writeheader();w.writerows(rows)
    print('Wrote',len(rows),'unique listings to',CURRENT/'calavera_diamonds.csv')
    if rows: print('Sample:',json.dumps(rows[:3],indent=2))
    else: print('WARNING: Calavera 0 means uncollected, not zero inventory.')
if __name__=='__main__':main()
