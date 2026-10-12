"""Inspect Calavera OTHER product pages, retaining raw HTML and conservative findings.
Run: py calavera_details.py --limit 38
No guesswork: missing dimensions or cut labels remain unverified.
"""
import argparse,csv,re,time,json,html
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from storage import CURRENT, RAW, ensure_layout

HEADERS={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154.0.0.0 Safari/537.36','Accept':'text/html,application/xhtml+xml'}
FIELDS=['id','title','carat','color','clarity','price_usd','url','http_status','shape','detail_cut','length_mm','width_mm','depth_mm','ratio','depth_pct','table_pct','polish','symmetry','lab','certificate','certificate_url','review_status','error']
def text_or_blank(value):return str(value or '').strip()
def inspect(row,raw):
    soup=BeautifulSoup(raw,'html.parser')
    for el in soup(['script','style','noscript','svg']):el.decompose()
    visible=' '.join(soup.stripped_strings)
    # The embedded Next.js payload may contain spec text absent from visible HTML.
    body=html.unescape(raw.replace('\\"','"'))
    text=visible+' '+body
    def embedded(name):
        found=re.search(r'"'+re.escape(name)+r'"\s*:\s*(?:"([^"]*)"|(-?\d+(?:\.\d+)?))',body,re.I)
        return (found.group(1) if found and found.group(1) is not None else found.group(2)) if found else ''
    cut=''
    for term in ('HEXAGONAL MODIFIED STEP CUT','DUTCH MARQUISE','MODIFIED BRILLIANT','BRILLIANT CUT','STEP CUT'):
        if re.search(re.escape(term),text,re.I):cut=term;break
    dims=re.search(r'(?<!\d)(\d{2}\.\d{1,2})\s*[x×X]\s*(\d\.\d{1,2})(?:\s*[x×X]\s*(\d\.\d{1,2}))?\s*(?:mm)?',text,re.I)
    # Only extract a report number when near an explicit grading-lab or report label.
    cert=re.search(r'(?:IGI|GIA|HRD|report\s*(?:number|no\.?|#)|certificate\s*(?:number|no\.?|#))[^0-9]{0,45}(\d{7,12})',text,re.I)
    length,width,depth=('','','') if not dims else dims.groups(default='')
    length=embedded('lengthMm') or length;width=embedded('widthMm') or width;depth=embedded('depthMm') or depth
    ratio=embedded('ratio') or (f'{float(length)/float(width):.3f}' if length and width else '')
    lab=embedded('lab')
    certificate=embedded('number') or (cert.group(1) if cert else '')
    if certificate and certificate.upper().startswith('LG'):certificate=certificate[2:]
    if cut=='HEXAGONAL MODIFIED STEP CUT':status='EXCLUDE - specified cut'
    elif cut=='DUTCH MARQUISE':status='POTENTIAL DUTCH - verify imagery/report'
    elif lab.upper()=='IGI' and certificate:status='IGI FOUND - verify report cut style'
    elif lab and lab.upper()!='IGI':status='EXCLUDE - no IGI certificate'
    else:status='UNVERIFIED - inspect report/image'
    return {'shape':embedded('shape'),'detail_cut':cut,'length_mm':length,'width_mm':width,'depth_mm':depth,'ratio':ratio,
            'depth_pct':embedded('depthPct'),'table_pct':embedded('tablePct'),'polish':embedded('polish'),
            'symmetry':embedded('symmetry'),'lab':lab,'certificate':certificate,
            'certificate_url':embedded('pdfUrl'),'review_status':status}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',default=str(CURRENT/'calavera_diamonds.csv'));ap.add_argument('--limit',type=int,default=100);ap.add_argument('--delay',type=float,default=1.5);args=ap.parse_args()
    with open(args.input,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    rows=[r for r in rows if any(label in (r.get('title') or '').lower() for label in ('other','hexagonal')) and 'square radiant' not in (r.get('title') or '').lower()]
    print(f'Found {len(rows)} OTHER/HEXAGONAL listings; inspecting first {args.limit}.')
    ensure_layout();session=requests.Session();results=[];rawdir=RAW/'calavera'/'details';rawdir.mkdir(parents=True,exist_ok=True)
    for i,r in enumerate(rows[:args.limit],1):
        record={k:text_or_blank(r.get(k)) for k in FIELDS};record['review_status']='UNVERIFIED - not inspected'
        try:
            resp=session.get(r['url'],headers=HEADERS,timeout=40);record['http_status']=resp.status_code
            (rawdir/(re.sub('[^a-zA-Z0-9_-]','_',r['id'])+'.html')).write_text(resp.text,encoding='utf-8')
            resp.raise_for_status();record.update(inspect(r,resp.text))
        except Exception as exc:record['error']=str(exc);record['review_status']='UNVERIFIED - fetch error'
        results.append(record)
        print(i,'/',min(args.limit,len(rows)),r.get('title'),record['review_status'],record['length_mm'],record['width_mm'])
        if i<len(rows):time.sleep(args.delay)
    with (CURRENT/'calavera_other_details.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerows(results)
    print('Wrote',len(results),'rows to',CURRENT/'calavera_other_details.csv')
if __name__=='__main__':main()
