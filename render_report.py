"""Render the purchase-confidence dashboard as self-contained sortable HTML."""
from __future__ import annotations

import argparse
import html
from datetime import datetime

from storage import REPORTS, read_json


def esc(value): return html.escape(str(value if value not in (None, '') else '—'))
def cash(value): return '—' if value in (None, '') else f'${float(value):,.2f}'


def badges(text, kind='warn'):
    items = [item.strip() for item in str(text or '').split(';') if item.strip()]
    return ''.join(f'<span class="badge {kind}">{esc(item)}</span>' for item in items) or '<span class="badge good">No recorded warnings</span>'


def offer_cards(offers):
    cards = []
    for offer in offers:
        promo = offer.get('promo_status') == 'estimated_unverified'
        media = []
        if offer.get('video_url'): media.append(f'<a href="{esc(offer["video_url"])}" target="_blank" rel="noopener">360° video</a>')
        if offer.get('image_url'): media.append(f'<a href="{esc(offer["image_url"])}" target="_blank" rel="noopener">image</a>')
        freshness = offer.get('freshness_status', 'unknown')
        cards.append(f'''<article class="offer">
          <div><strong>{esc(offer.get('retailer'))}</strong><small>{esc(offer.get('availability'))} · {esc(freshness)} ({esc(offer.get('age_days'))} days)</small></div>
          <div class="price"><strong>{cash(offer.get('effective_price_usd'))}{' estimated' if promo else ''}</strong><small>Listed {cash(offer.get('listed_price'))} {esc(offer.get('currency'))}</small></div>
          <div class="links"><a href="{esc(offer.get('product_url'))}" target="_blank" rel="noopener">retailer listing</a>{' · ' + ' · '.join(media) if media else ''}</div>
          <div class="meta">Last checked {esc(offer.get('last_checked_at'))}{' · ' + esc(offer.get('promo_code')) + ' must be verified' if promo else ''}</div>
        </article>''')
    return ''.join(cards)


def vendor_matrix(checks):
    if not checks:
        return '<p>No vendor lookup results. Run the complete pipeline.</p>'
    cards = []
    for item in checks:
        status = item.get('status')
        url = item.get('product_url') or item.get('query_url')
        link = f'<a href="{esc(url)}" target="_blank" rel="noopener">source ↗</a>' if url else ''
        cards.append(f'''<article class="vendor" style="background:white;border:1px solid var(--line);border-radius:11px;padding:12px"><strong>{esc(item.get('retailer'))}</strong>
          <span class="badge {('good' if status == 'priced' else 'warn')}">{esc(status)}</span>
          <div>{cash(item.get('price'))}</div><small>{esc(item.get('notes'))}</small>{link}</article>''')
    return '<div class="vendor-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:9px">' + ''.join(cards) + '</div>'


def ranking_rationale(d):
    strengths = [f"Dimensional fit {d.get('dimension_fit_score')}/100"]
    if float(d.get('preference_penalty') or 0) == 0:
        strengths.append('Ratio, table, and depth are within preferred ranges')
    if d.get('certificate_evidence_status') == 'validated':
        strengths.append('Retained IGI PDF independently validated')
    if d.get('offers') and len(d['offers']) > 1:
        strengths.append(f"{len(d['offers'])} retailer offers identified")
    deductions = []
    if float(d.get('preference_penalty') or 0) > 0:
        deductions.append(f"Proportion penalty {d.get('preference_penalty')}")
    if float(d.get('evidence_penalty') or 0) > 0:
        deductions.append(f"Evidence penalty {d.get('evidence_penalty')}")
    for warning in str(d.get('warnings') or '').split(';'):
        warning = warning.strip()
        if warning and warning not in deductions: deductions.append(warning)
    return f'''<section style="margin:14px 0;background:white;border:1px solid var(--line);border-radius:11px;padding:14px">
      <h3>Why this diamond is ranked #{esc(d.get('computed_rank'))}</h3>
      <p><strong>Diamond score {esc(d.get('overall_score'))}/100:</strong> 100 − 5 × (dimension penalty {esc(d.get('dimension_penalty'))} + proportion penalty {esc(d.get('preference_penalty'))} + evidence penalty {esc(d.get('evidence_penalty'))}).</p>
      <p><strong>Value score {esc(d.get('value_score'))}/100:</strong> applies an additional price component of {esc(d.get('value_component'))}; price does not change the diamond-quality rank.</p>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px"><div><strong>Reasons in favor</strong><ul>{''.join(f'<li>{esc(item)}</li>' for item in strengths)}</ul></div><div><strong>Deductions and open questions</strong><ul>{''.join(f'<li>{esc(item)}</li>' for item in deductions) or '<li>None recorded</li>'}</ul></div></div>
    </section>'''


def methodology():
    return '''<details open style="margin:22px 0;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;box-shadow:var(--shadow)">
      <summary style="font-size:17px">How the rankings are calculated</summary>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:14px">
        <section><h3>1. Qualification gate</h3><p>D/E color, VS1 or better, Excellent polish and symmetry, and IGI Hexagonal Modified Brilliant are required. Step cuts are rejected.</p></section>
        <section><h3>2. Dimensional fit</h3><p>Target: 15.5 × 7.8 mm. Penalty = ((length − 15.5) / 0.35)² + ((width − 7.8) / 0.20)². Width is intentionally weighted more heavily.</p></section>
        <section><h3>3. Soft preferences</h3><p>Ratio 1.90–2.05, table 55–65%, and depth 58–67% have no penalty. Small deviations lower the score but do not automatically reject a stone.</p></section>
        <section><h3>4. Evidence</h3><p>Unverified cutting style and missing optical review lower confidence. IGI data and stone-specific imagery are tracked separately from retailer labels.</p></section>
        <section><h3>5. Diamond score</h3><p>100 − 5 × (dimension + proportion + evidence penalties). Higher is better. Price is excluded so the best criteria match remains visible.</p></section>
        <section><h3>6. Value and price</h3><p>The value score adds cheapest effective price ÷ 4,000 as a modest penalty. Retailer prices are also compared directly; promotions remain conditional until checkout.</p></section>
      </div><p><strong>Important:</strong> Neither score predicts brilliance, bow tie, scintillation, contrast, windowing, or real-world appearance. Those require structured optical review.</p>
    </details>'''


def detail(d):
    review = d.get('optical_review') or {}
    optical_fields = ('outline','faceting','bow_tie','central_darkness','tips','windowing','symmetry','tilt_performance')
    optical = ''.join(f'<div><small>{name.replace("_", " ")}</small><strong>{esc(review.get(name))}</strong></div>' for name in optical_fields)
    return f'''<tr class="details"><td colspan="9"><details><summary>Evidence, readiness blockers, and {esc(d.get('offer_count'))} offers</summary>
      {ranking_rationale(d)}
      <div class="detail-grid"><section><h3>Purchase readiness</h3>{badges(d.get('readiness_blockers'))}<p>{esc(d.get('score_explanation'))}</p></section>
      <section><h3>IGI evidence</h3><p>Status: <strong>{esc(d.get('certificate_evidence_status'))}</strong></p><p>File: {esc(d.get('certificate_file'))}<br>Checked: {esc(d.get('certificate_checked_at'))}</p>{badges(d.get('certificate_mismatches'))}</section>
      <section><h3>Exact-stone market coverage</h3><p><strong>{esc(d.get('exact_certificate_searched'))}/{esc(d.get('retailer_universe'))}</strong> searched for this IGI number.</p><p>{esc(d.get('matching_active_offers'))} offers found · {esc(d.get('fresh_price_observations'))} fresh price observations · {esc(d.get('live_availability_confirmed'))} availability confirmations · {esc(d.get('checkout_verified_offers'))} checkout verified.</p><p>{esc(d.get('searched_no_match'))} searched without a match · {esc(d.get('matching_archived_sources'))} archived sources.</p><p>Not searched: {esc(d.get('coverage_not_searched'))}</p></section></div>
      <section><h3>Structured optical review</h3><div class="optical">{optical}</div><p>{esc(d.get('optical_notes'))}</p></section>
      <section><h3>All configured vendor checks</h3>{vendor_matrix(d.get('vendor_price_checks', []))}</section>
      <section><h3>Matched retailer offers</h3><div class="offers">{offer_cards(d.get('offers', []))}</div></section>
    </details></td></tr>'''


def row(d):
    dimensions = f"{esc(d.get('length_mm'))} × {esc(d.get('width_mm'))} × {esc(d.get('height_mm'))}"
    ready = str(d.get('purchase_readiness') or 'NOT READY')
    ready_class = 'good' if ready == 'READY TO PURCHASE' else 'pending' if ready.startswith('READY') else 'bad'
    return f'''<tr class="diamond" data-rank="{esc(d.get('computed_rank'))}" data-price="{esc(d.get('cheapest_effective_price'))}" data-fit="{esc(d.get('dimension_fit_score'))}" data-score="{esc(d.get('overall_score'))}">
      <td><span class="rank">{esc(d.get('computed_rank'))}</span></td>
      <td><strong>{esc(d.get('certificate'))}</strong><a href="{esc(d.get('certificate_url'))}" target="_blank" rel="noopener">IGI lookup ↗</a></td>
      <td><strong>{esc(d.get('carat'))} ct · {esc(d.get('color'))}/{esc(d.get('clarity'))}</strong><small>{dimensions} mm · ratio {esc(d.get('ratio'))}</small></td>
      <td><strong>{esc(d.get('table_pct'))}% / {esc(d.get('depth_pct'))}%</strong><small>table / depth</small></td>
      <td><span class="badge {('good' if d.get('certificate_evidence_status') == 'validated' else 'warn')}">IGI {esc(d.get('certificate_evidence_status'))}</span><span class="badge pending">Optical {esc(d.get('optical_review_status'))}</span></td>
      <td><span class="badge {ready_class}">{esc(ready)}</span></td>
      <td><strong>{esc(d.get('overall_score'))}/100</strong><small>Diamond criteria · value {esc(d.get('value_score'))}/100</small></td>
      <td><strong>{cash(d.get('cheapest_effective_price'))}</strong><small>{esc(d.get('cheapest_retailer'))}</small></td>
      <td>{badges(d.get('warnings'))}</td></tr>{detail(d)}'''


def render(data, generated_at=None):
    generated_at = generated_at or datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')
    best = data[0] if data else {}
    rows = ''.join(row(item) for item in data)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Diamond Finder · Purchase Confidence</title><style>
:root{{--ink:#18211e;--muted:#64716c;--paper:#f3f0e8;--card:#fffdf8;--line:#d9d4c9;--green:#204f41;--mint:#dcece5;--amber:#fff0ca;--red:#f8deda;--shadow:0 16px 45px #1f2b2616}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:14px/1.5 Inter,system-ui,sans-serif}}a{{color:var(--green)}}main{{max-width:1500px;margin:auto;padding:42px 28px 70px}}header{{display:flex;justify-content:space-between;align-items:end;gap:24px}}h1{{font:500 clamp(34px,5vw,62px)/1 Georgia,serif;margin:6px 0}}h3{{margin:0 0 8px}}.eyebrow{{color:#9a6c22;text-transform:uppercase;letter-spacing:.15em;font-size:11px;font-weight:800}}.muted,small,.meta{{display:block;color:var(--muted);font-size:12px}}.summary{{display:grid;grid-template-columns:2fr repeat(3,1fr);gap:12px;margin:26px 0}}.tile{{padding:18px;background:var(--card);border:1px solid var(--line);border-radius:15px;box-shadow:var(--shadow)}}.hero{{background:var(--green);color:white}}.metric{{font:500 27px Georgia,serif;margin-top:5px}}.hero .muted{{color:#d7e9e2}}.controls{{margin:22px 0 10px}}select{{padding:9px;border:1px solid var(--line);border-radius:8px;background:white}}.wrap{{overflow:auto;background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}}table{{border-collapse:collapse;width:100%;min-width:1280px}}th{{text-align:left;background:#ebe7dd;color:var(--muted);padding:12px;font-size:10px;text-transform:uppercase;letter-spacing:.08em}}td{{padding:15px 12px;border-top:1px solid var(--line);vertical-align:top}}td>a{{display:block;font-size:12px}}.rank{{display:grid;place-items:center;width:32px;height:32px;border-radius:50%;background:var(--green);color:white}}.badge{{display:inline-block;padding:4px 8px;border-radius:99px;font-size:10px;margin:0 3px 4px 0;max-width:260px}}.good{{background:var(--mint)}}.warn,.pending{{background:var(--amber)}}.bad{{background:var(--red)}}.details td{{background:#faf8f2;padding:0 14px 14px}}details{{border-left:3px solid var(--mint);padding:9px 13px}}summary{{cursor:pointer;font-weight:700;color:var(--green)}}.detail-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0}}.detail-grid section,.offer{{background:white;border:1px solid var(--line);border-radius:11px;padding:12px}}.optical{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}.optical>div{{padding:8px;background:white;border:1px solid var(--line);border-radius:8px}}.offers{{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:9px}}.offer{{display:grid;grid-template-columns:1fr auto;gap:7px}}.price{{text-align:right}}.links,.meta{{grid-column:1/-1}}footer{{margin-top:20px;color:var(--muted);max-width:900px}}@media(max-width:850px){{main{{padding:24px 14px}}header{{display:block}}.summary{{grid-template-columns:1fr 1fr}}.hero{{grid-column:1/-1}}.detail-grid,.optical{{grid-template-columns:1fr}}}}@media print{{body{{background:white}}.controls{{display:none}}.tile,.wrap{{box-shadow:none}}}}
</style></head><body><main><header><div><div class="eyebrow">Diamond Finder · evidence before confidence</div><h1>Purchase-confidence dossier</h1><p class="muted">One row per physical IGI diamond. Price, certification, optical evidence, coverage, and buyer protection remain separate checks.</p></div><div class="muted">Generated {esc(generated_at)}</div></header>
<section class="summary"><div class="tile hero"><small>Preference leader</small><div class="metric">{esc(best.get('certificate'))}</div><div class="muted">{cash(best.get('cheapest_effective_price'))} at {esc(best.get('cheapest_retailer'))} · {esc(best.get('purchase_readiness'))}</div></div><div class="tile"><small>Unique stones</small><div class="metric">{len(data)}</div></div><div class="tile"><small>Purchase ready</small><div class="metric">{sum(d.get('purchase_readiness') == 'READY TO PURCHASE' for d in data)}</div></div><div class="tile"><small>Validated IGI files</small><div class="metric">{sum(d.get('certificate_evidence_status') == 'validated' for d in data)}</div></div></section>
{methodology()}
<div class="controls"><label for="sort">Sort by </label><select id="sort"><option value="rank">overall ranking</option><option value="price">lowest price</option><option value="fit">dimensional fit</option><option value="score">overall score</option></select></div>
<div class="wrap"><table id="diamonds"><thead><tr><th>Rank</th><th>IGI</th><th>Diamond</th><th>Proportions</th><th>Evidence</th><th>Readiness</th><th>Score</th><th>Best offer</th><th>Warnings</th></tr></thead><tbody>{rows}</tbody></table></div><footer>A high preference score does not establish brilliance or optical performance. Do not buy until the retained IGI report, laser inscription, structured visual review, live checkout total, availability, and seller protections are confirmed.</footer></main><script>const s=document.querySelector('#sort'),b=document.querySelector('#diamonds tbody');s.addEventListener('change',()=>{{const p=[...b.querySelectorAll('tr.diamond')].map(r=>[r,r.nextElementSibling]);const desc=['fit','score'].includes(s.value);p.sort((a,c)=>{{const av=parseFloat(a[0].dataset[s.value]||'Infinity'),cv=parseFloat(c[0].dataset[s.value]||'Infinity');return desc?cv-av:av-cv}});p.forEach(x=>x.forEach(r=>b.appendChild(r)))}});</script></body></html>'''


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--input', default='dashboard_data.json'); parser.add_argument('--output', default='diamond_report.html'); args = parser.parse_args()
    data = read_json(REPORTS / args.input); (REPORTS / args.output).write_text(render(data), encoding='utf-8')
    print(f'Wrote styled report to reports/{args.output}')


if __name__ == '__main__': main()
