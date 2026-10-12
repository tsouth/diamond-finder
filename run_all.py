"""Run collectors then merge. Use --offline to merge existing CSVs only."""
import argparse, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

from provenance import new_run_id, snapshot

def main():
    p=argparse.ArgumentParser();p.add_argument('--mikado-pages',type=int,default=10);p.add_argument('--offline',action='store_true');p.add_argument('--stienhardt-pages',type=int,default=10);p.add_argument('--aurelinne-pages',type=int,default=20);p.add_argument('--calavera-pages',type=int,default=5);p.add_argument('--aurelinne-target',action=argparse.BooleanOptionalAction,default=True);a=p.parse_args()
    base=Path(__file__).parent
    run_id=new_run_id(); snapshot(base,run_id,'before')
    statuses=[]
    aurelinne=['aurelinne_probe.py','--pages',str(a.aurelinne_pages)] + (['--target'] if a.aurelinne_target else [])
    commands=[] if a.offline else [
        ['stienhardt_probe.py','--pages',str(a.stienhardt_pages)],
        aurelinne,
        ['calavera_probe.py','--pages',str(a.calavera_pages)],
        ['mikado_probe.py','--pages',str(a.mikado_pages)]]
    for cmd in commands:
        print('\n===',cmd[0],'===',flush=True)
        result=subprocess.run([sys.executable,*cmd],cwd=base)
        statuses.append({'command':cmd,'returncode':result.returncode})
        if result.returncode: print(f'WARNING: {cmd[0]} failed; comparison may contain older data.',flush=True)
    print('\n=== Merge ===',flush=True)
    merge=subprocess.call([sys.executable,'compare_diamonds.py'],cwd=base)
    statuses.append({'command':['compare_diamonds.py'],'returncode':merge})
    print('\n=== Cross-retailer prices ===',flush=True)
    prices=subprocess.call([sys.executable,'cross_retailer_prices.py'],cwd=base)
    statuses.append({'command':['cross_retailer_prices.py'],'returncode':prices})
    print('\n=== Market coverage ===',flush=True)
    coverage=subprocess.call([sys.executable,'market_coverage.py'],cwd=base)
    statuses.append({'command':['market_coverage.py'],'returncode':coverage})
    print('\n=== Exact-certificate vendor prices ===',flush=True)
    vendor_prices=subprocess.call([sys.executable,'vendor_prices.py', *(['--offline'] if a.offline else [])],cwd=base)
    statuses.append({'command':['vendor_prices.py'],'returncode':vendor_prices})
    print('\n=== Canonical shortlist ===',flush=True)
    shortlist=subprocess.call([sys.executable,'shortlist.py'],cwd=base)
    statuses.append({'command':['shortlist.py'],'returncode':shortlist})
    print('\n=== Styled report ===',flush=True)
    report=subprocess.call([sys.executable,'render_report.py'],cwd=base)
    statuses.append({'command':['render_report.py'],'returncode':report})
    snapshot(base,run_id,'after')
    run_dir=base/'data'/'runs'/run_id
    (run_dir/'run_status.json').write_text(json.dumps({
        'run_id':run_id,'finished_at':datetime.now(timezone.utc).isoformat(),
        'offline':a.offline,'commands':statuses,
    },indent=2),encoding='utf-8')
    print('Audit snapshot:',run_dir,flush=True)
    return merge or prices or coverage or vendor_prices or shortlist or report
if __name__=='__main__':raise SystemExit(main())
