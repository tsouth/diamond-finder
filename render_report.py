"""Render the purchase-confidence dashboard as self-contained sortable HTML."""
from __future__ import annotations

import argparse
import html
import re
from datetime import datetime

from storage import REPORTS, read_json


def esc(value): return html.escape(str(value if value not in (None, '') else '—'))
def cash(value):
    if value in (None, ''): return '—'
    amount = float(value)
    return f'<span class="money" data-usd="{amount:.2f}">${amount:,.2f}</span>'


def friendly(value):
    """Turn internal validation messages into plain, buyer-friendly language."""
    text = str(value or '')
    replacements = {
        'structured optical review incomplete': 'The photos and video still need a closer look',
        'structured optical review is incomplete': 'The photos and video still need a closer look',
        'retained IGI report not validated': 'The saved IGI report still needs to be verified',
        'retained IGI report has not been validated': 'The saved IGI report still needs to be verified',
        'missing stone-specific 360 video': 'No 360° video is available for this stone yet',
        'no fresh, confirmed-available offer': 'No retailer has recently confirmed that it is in stock',
        'seller protection terms are not recorded': 'Return and buyer-protection terms still need review',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r'length ([\d.]+) mm differs from target ([\d.]+) mm', r'At \1 mm long, it is a little different from the \2 mm target', text)
    text = re.sub(r'ratio ([\d.]+) outside preferred ([\d.]+-[\d.]+)', r'The \1 shape ratio falls just outside the preferred \2 range', text)
    text = re.sub(r'depth ([\d.]+)% outside preferred ([\d-]+)%', r'The \1% depth falls just outside the preferred \2% range', text)
    return text


def badges(text, kind='warn'):
    items = [item.strip() for item in str(text or '').split(';') if item.strip()]
    return ''.join(f'<span class="badge {kind}">{esc(friendly(item))}</span>' for item in items) or '<span class="badge good">Nothing to flag</span>'


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
          <div class="price"><strong>{cash(offer.get('effective_price_usd'))}{' estimated' if promo else ''}</strong><small>Retailer price: {cash(offer.get('listed_price'))} {esc(offer.get('currency'))}</small></div>
          <div class="links"><a href="{esc(offer.get('product_url'))}" target="_blank" rel="noopener">View at retailer</a>{' · ' + ' · '.join(media) if media else ''}</div>
          <div class="meta">Price checked {esc(offer.get('last_checked_at'))}{' · Confirm the ' + esc(offer.get('promo_code')) + ' discount at checkout' if promo else ''}</div>
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


def stone_media(d):
    offers = d.get('offers') or []
    image_url = next((o.get('image_url') for o in offers if o.get('image_url')), '')
    video_url = next((o.get('video_url') for o in offers if o.get('video_url')), '')
    if not image_url and not video_url:
        return '<p class="muted">No stone-specific image or 360° view is available yet.</p>'
    image = (f'<a href="{esc(image_url)}" target="_blank" rel="noopener" style="display:block;flex:0 0 260px">'
             f'<img src="{esc(image_url)}" alt="Stone-specific view of diamond {esc(d.get("certificate"))}" loading="lazy" style="display:block;width:260px;max-width:100%;max-height:210px;object-fit:contain;border-radius:9px;background:#f5f5f2"></a>') if image_url else ''
    rotation = f'<a class="media-button" href="{esc(video_url)}" target="_blank" rel="noopener">View interactive 360° ↗</a>' if video_url else '<span class="media-note">360° rotation not supplied by the retailer</span>'
    return f'<div style="display:flex;align-items:center;flex-wrap:wrap;gap:18px;margin:10px 0 18px;padding:14px;background:white;border:1px solid var(--line);border-radius:12px">{image}<div><strong>Stone-specific view</strong><p class="muted">This is the retailer image for this exact IGI number.</p>{rotation}</div></div>'


def ranking_rationale(d):
    strengths = [f"Its size is a {d.get('dimension_fit_score')}/100 match for your target"]
    if float(d.get('preference_penalty') or 0) == 0:
        strengths.append('Its shape, table, and depth are all within your preferred ranges')
    if d.get('certificate_evidence_status') == 'validated':
        strengths.append('The saved IGI report has been independently checked')
    if d.get('offers') and len(d['offers']) > 1:
        strengths.append(f"It is available from {len(d['offers'])} retailers")
    deductions = []
    if float(d.get('preference_penalty') or 0) > 0:
        deductions.append('One or more proportions sit outside your preferred range')
    if float(d.get('evidence_penalty') or 0) > 0:
        deductions.append('Some supporting evidence is still missing')
    for warning in str(d.get('warnings') or '').split(';'):
        warning = warning.strip()
        if warning and friendly(warning) not in deductions: deductions.append(friendly(warning))
    return f'''<section style="margin:14px 0;background:white;border:1px solid var(--line);border-radius:11px;padding:14px">
      <h3>Why this one is #{esc(d.get('computed_rank'))}</h3>
      <span class="visually-hidden">Why this diamond is ranked #{esc(d.get('computed_rank'))}</span>
      <p><strong>Diamond score: {esc(d.get('overall_score'))}/100.</strong> This reflects how closely the stone matches your preferred size and proportions, plus how much evidence is available.</p>
      <p><strong>Value score: {esc(d.get('value_score'))}/100.</strong> This also considers price. Price never changes the underlying quality-match ranking.</p>
      <details class="calculation"><summary>See the calculation</summary><p>100 − 5 × (size difference {esc(d.get('dimension_penalty'))} + proportion difference {esc(d.get('preference_penalty'))} + missing evidence {esc(d.get('evidence_penalty'))}). The value calculation adds a price factor of {esc(d.get('value_component'))}.</p></details>
      <div class="pros-cons"><div><strong>What stands out</strong><ul>{''.join(f'<li>{esc(item)}</li>' for item in strengths)}</ul></div><div><strong>What to check next</strong><ul>{''.join(f'<li>{esc(item)}</li>' for item in deductions) or '<li>Nothing else to check right now</li>'}</ul></div></div>
    </section>'''


def methodology():
    return '''<details class="methodology">
      <summary>How we picked the best matches</summary>
      <p class="muted">Start here if you want to understand the recommendations. The detailed math is available, but you do not need it to compare the stones.</p>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:14px">
        <section><h3>First, the essentials</h3><p>Only D/E color, VS1 or better, Excellent polish and symmetry, and the correct IGI cutting style make the list.</p></section>
        <section><h3>Then, the right size</h3><p>Stones closest to your 15.5 × 7.8 mm target rank higher. Width matters a little more because it has a strong effect on the face-up look.</p></section>
        <section><h3>Your preferred shape</h3><p>A 1.90–2.05 ratio, 55–65% table, and 58–67% depth are preferred. A small miss lowers the match score; it does not automatically rule a stone out.</p></section>
        <section><h3>Confidence matters</h3><p>A verified IGI report and stone-specific photos or video make a recommendation more trustworthy. Retailer descriptions alone are not enough.</p></section>
        <section><h3>Diamond score</h3><p>This is the overall match for your size, proportions, and available evidence. Higher is better, and price is deliberately left out.</p></section>
        <section><h3>Value score</h3><p>This adds price to the picture, helping you spot a strong match at a competitive price. Any promotion should still be confirmed at checkout.</p></section>
      </div><p><strong>One important note:</strong> Neither score predicts brilliance or how the diamond will look in person. Photos, video, and a careful visual review are still essential.</p>
      <span class="visually-hidden">How the rankings are calculated. Neither score predicts brilliance.</span>
    </details>'''


def detail(d):
    return f'''<tr class="details"><td colspan="7"><details><summary>View this stone and compare {esc(d.get('offer_count'))} offers</summary>
      <section><h3>See the actual stone</h3>{stone_media(d)}</section>
      <section><h3>Available offers</h3><div class="offers">{offer_cards(d.get('offers', []))}</div></section>
    </details></td></tr>'''


def row(d):
    dimensions = f"{esc(d.get('length_mm'))} × {esc(d.get('width_mm'))} × {esc(d.get('height_mm'))}"
    ready = str(d.get('purchase_readiness') or 'NOT READY')
    ready_class = 'good' if ready == 'READY TO PURCHASE' else 'pending' if ready.startswith('READY') else 'bad'
    return f'''<tr class="diamond" data-rank="{esc(d.get('computed_rank'))}" data-price="{esc(d.get('cheapest_effective_price'))}" data-fit="{esc(d.get('dimension_fit_score'))}" data-score="{esc(d.get('overall_score'))}">
      <td><span class="rank">{esc(d.get('computed_rank'))}</span></td>
      <td><strong>{esc(d.get('certificate'))}</strong><a href="{esc(d.get('certificate_url'))}" target="_blank" rel="noopener">View IGI report ↗</a></td>
      <td><strong>{esc(d.get('carat'))} ct · {esc(d.get('color'))}/{esc(d.get('clarity'))}</strong><small>{dimensions} mm · ratio {esc(d.get('ratio'))}</small></td>
      <td><strong>{esc(d.get('table_pct'))}% / {esc(d.get('depth_pct'))}%</strong><small>table / depth</small></td>
      <td><strong>{esc(d.get('overall_score'))}/100</strong><small>Match score · value {esc(d.get('value_score'))}/100</small></td>
      <td><strong>{cash(d.get('cheapest_effective_price'))}</strong><small>{esc(d.get('cheapest_retailer'))}</small></td>
      <td>{badges(d.get('warnings'))}</td></tr>{detail(d)}'''


def mobile_styles():
    return '''<style>
@media (max-width:760px){
  body{font-size:15px} main{padding:20px 12px 48px} header{display:block} h1{font-size:38px;line-height:1.05}
  .header-tools{margin-top:18px;text-align:left;white-space:normal}.header-tools select{min-width:140px}
  .summary{grid-template-columns:1fr;margin:20px 0}.hero{grid-column:auto}.tile{padding:16px}
  .methodology>div{grid-template-columns:1fr!important}.controls{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:10px}.controls select{width:100%;min-height:44px}
  .wrap{overflow:visible;background:transparent;border:0;box-shadow:none}table{display:block;min-width:0}thead{display:none}tbody{display:block}
  tr.diamond{display:grid;grid-template-columns:1fr 1fr;margin:0 0 0;background:var(--card);border:1px solid var(--line);border-radius:16px 16px 0 0;box-shadow:var(--shadow);overflow:hidden}
  tr.diamond td{display:block;min-width:0;padding:13px 14px;border-top:1px solid var(--line)}
  tr.diamond td:before{display:block;margin-bottom:3px;color:var(--muted);font-size:10px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}
  tr.diamond td:nth-child(1):before{content:'Pick'}tr.diamond td:nth-child(2):before{content:'IGI report'}tr.diamond td:nth-child(3):before{content:'Diamond'}tr.diamond td:nth-child(4):before{content:'Shape details'}tr.diamond td:nth-child(5):before{content:'Match'}tr.diamond td:nth-child(6):before{content:'Best price'}tr.diamond td:nth-child(7):before{content:'Worth knowing'}
  html[lang="ja"] tr.diamond td:nth-child(1):before{content:'順位'}html[lang="ja"] tr.diamond td:nth-child(2):before{content:'IGIレポート'}html[lang="ja"] tr.diamond td:nth-child(3):before{content:'ダイヤモンド'}html[lang="ja"] tr.diamond td:nth-child(4):before{content:'形状の詳細'}html[lang="ja"] tr.diamond td:nth-child(5):before{content:'マッチ度'}html[lang="ja"] tr.diamond td:nth-child(6):before{content:'最安価格'}html[lang="ja"] tr.diamond td:nth-child(7):before{content:'確認ポイント'}
  tr.diamond td:nth-child(1){grid-column:1/-1;border-top:0;padding-bottom:8px}tr.diamond td:nth-child(7){grid-column:1/-1}
  .rank{width:38px;height:38px}.badge{font-size:12px;max-width:100%;white-space:normal}
  tr.details{display:block;margin:0 0 20px}tr.details>td{display:block;padding:0 10px 12px;background:#faf8f2;border:1px solid var(--line);border-top:0;border-radius:0 0 16px 16px;box-shadow:var(--shadow)}
  tr.details details{padding:12px 4px;border-left:0}tr.details summary{min-height:44px;display:flex;align-items:center}
  .offers,.offer{grid-template-columns:1fr}.price{text-align:left}.links,.meta{grid-column:auto}.offer a{display:inline-block;min-height:40px;padding-top:8px}
  footer{font-size:13px}.stone-media{flex-direction:column}
}
@media (max-width:480px){
  h1{font-size:33px}.summary{grid-template-columns:1fr}tr.diamond{grid-template-columns:1fr}tr.diamond td, tr.diamond td:nth-child(1), tr.diamond td:nth-child(7){grid-column:1}
}
</style>'''


def render(data, generated_at=None):
    generated_at = generated_at or datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')
    best = data[0] if data else {}
    rows = ''.join(row(item) for item in data)
    return rf'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Diamond Finder · Purchase Confidence</title><style>
:root{{--ink:#18211e;--muted:#64716c;--paper:#f3f0e8;--card:#fffdf8;--line:#d9d4c9;--green:#204f41;--mint:#dcece5;--amber:#fff0ca;--red:#f8deda;--shadow:0 16px 45px #1f2b2616}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 Inter,system-ui,sans-serif}}a{{color:var(--green)}}main{{max-width:1500px;margin:auto;padding:42px 28px 70px}}header{{display:flex;justify-content:space-between;align-items:end;gap:24px}}h1{{font:500 clamp(34px,5vw,62px)/1 Georgia,serif;margin:6px 0}}h3{{margin:0 0 8px}}.eyebrow{{color:#9a6c22;text-transform:uppercase;letter-spacing:.15em;font-size:11px;font-weight:800}}.muted,small,.meta{{display:block;color:var(--muted);font-size:12px}}.header-tools{{text-align:right;white-space:nowrap}}.summary{{display:grid;grid-template-columns:2fr repeat(3,1fr);gap:12px;margin:26px 0}}.tile{{padding:18px;background:var(--card);border:1px solid var(--line);border-radius:15px;box-shadow:var(--shadow)}}.hero{{background:var(--green);color:white}}.metric{{font:500 27px Georgia,serif;margin-top:5px}}.hero .muted{{color:#d7e9e2}}.controls{{margin:22px 0 10px}}select{{padding:9px;border:1px solid var(--line);border-radius:8px;background:white}}.wrap{{overflow:auto;background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}}table{{border-collapse:collapse;width:100%;min-width:1280px}}th{{text-align:left;background:#ebe7dd;color:var(--muted);padding:12px;font-size:10px;text-transform:uppercase;letter-spacing:.08em}}td{{padding:15px 12px;border-top:1px solid var(--line);vertical-align:top}}td>a{{display:block;font-size:12px}}.rank{{display:grid;place-items:center;width:32px;height:32px;border-radius:50%;background:var(--green);color:white}}.badge{{display:inline-block;padding:5px 9px;border-radius:99px;font-size:11px;line-height:1.35;margin:0 3px 4px 0;max-width:280px}}.good{{background:var(--mint)}}.warn,.pending{{background:var(--amber)}}.bad{{background:var(--red)}}.details td{{background:#faf8f2;padding:0 14px 14px}}details{{border-left:3px solid var(--mint);padding:9px 13px}}summary{{cursor:pointer;font-weight:700;color:var(--green)}}.methodology{{margin:22px 0;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;box-shadow:var(--shadow)}}.methodology>summary{{font-size:17px}}.calculation{{margin:10px 0;border-left:0;padding:0}}.pros-cons{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.detail-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0}}.detail-grid section,.offer{{background:white;border:1px solid var(--line);border-radius:11px;padding:12px}}.optical{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}.optical>div{{padding:8px;background:white;border:1px solid var(--line);border-radius:8px}}.offers{{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:9px}}.offer{{display:grid;grid-template-columns:1fr auto;gap:7px}}.price{{text-align:right}}.links,.meta{{grid-column:1/-1}}.visually-hidden{{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}}footer{{margin-top:20px;color:var(--muted);max-width:900px}}@media(max-width:850px){{main{{padding:24px 14px}}header{{display:block}}.header-tools{{text-align:left;margin-top:16px}}.summary{{grid-template-columns:1fr 1fr}}.hero{{grid-column:1/-1}}.detail-grid,.optical,.pros-cons{{grid-template-columns:1fr}}}}@media print{{body{{background:white}}.controls{{display:none}}.tile,.wrap{{box-shadow:none}}}}
</style></head><body><main><header><div><div class="eyebrow">Diamond Finder · your shortlist, made clearer</div><h1>Find the diamond that feels right</h1><p class="muted">Compare your strongest matches, see the best available prices, and know what still needs checking before you buy.</p></div><div class="header-tools"><label for="language">Language </label><select id="language" aria-label="Language"><option value="en">English</option><option value="ja">日本語</option></select><div class="muted">Updated {esc(generated_at)}</div><div id="fx-note" class="muted" hidden></div></div></header>
{mobile_styles()}
<section class="summary"><div class="tile hero"><small>Best match right now</small><div class="metric">{esc(best.get('certificate'))}</div><div class="muted">From {cash(best.get('cheapest_effective_price'))} at {esc(best.get('cheapest_retailer'))} · {esc(best.get('purchase_readiness'))}</div></div><div class="tile"><small>Diamonds compared</small><div class="metric">{len(data)}</div></div><div class="tile"><small>Ready to buy</small><div class="metric">{sum(d.get('purchase_readiness') == 'READY TO PURCHASE' for d in data)}</div></div><div class="tile"><small>IGI reports verified</small><div class="metric">{sum(d.get('certificate_evidence_status') == 'validated' for d in data)}</div></div></section>
{methodology()}
<div class="controls"><label for="sort">Show me </label><select id="sort"><option value="rank">best matches first</option><option value="price-desc">highest prices first</option><option value="price">lowest prices first</option><option value="fit">closest size first</option><option value="score">highest match scores first</option></select></div>
<div class="wrap"><table id="diamonds"><thead><tr><th>Pick</th><th>IGI report</th><th>Diamond</th><th>Shape details</th><th>Match</th><th>Best price</th><th>Worth knowing</th></tr></thead><tbody>{rows}</tbody></table></div><footer>Use this shortlist as a confident starting point, not the final word. Before buying, confirm the IGI report and laser inscription, watch the stone-specific video, check the final checkout price and availability, and review the seller's return policy.</footer></main><script>
const s=document.querySelector('#sort'),b=document.querySelector('#diamonds tbody');s.addEventListener('change',()=>{{const p=[...b.querySelectorAll('tr.diamond')].map(r=>[r,r.nextElementSibling]);const desc=['price-desc','fit','score'].includes(s.value),key=s.value==='price-desc'?'price':s.value;p.sort((a,c)=>{{const av=parseFloat(a[0].dataset[key]||'Infinity'),cv=parseFloat(c[0].dataset[key]||'Infinity');return desc?cv-av:av-cv}});p.forEach(x=>x.forEach(r=>b.appendChild(r)))}});
const translations={{'Language':'言語','Diamond Finder · evidence before confidence':'Diamond Finder · 確信より先に根拠を','Purchase-confidence dossier':'購入判断レポート','One row per physical IGI diamond. Price, certification, optical evidence, coverage, and buyer protection remain separate checks.':'IGIダイヤモンド1石につき1行で表示します。価格、鑑定書、光学的根拠、市場網羅性、購入者保護は個別に確認します。','Preference leader':'条件に最も合う候補','Unique stones':'ユニークな石','Purchase ready':'購入準備完了','Validated IGI files':'検証済みIGIファイル','How the rankings are calculated':'ランキングの算出方法','1. Qualification gate':'1. 適格条件','2. Dimensional fit':'2. 寸法適合度','3. Soft preferences':'3. 推奨条件','4. Evidence':'4. 根拠','5. Diamond score':'5. ダイヤモンドスコア','6. Value and price':'6. 価値と価格','Sort by':'並び替え','overall ranking':'総合順位','lowest price':'価格の安い順','dimensional fit':'寸法適合度','overall score':'総合スコア','Rank':'順位','Diamond':'ダイヤモンド','Proportions':'プロポーション','Evidence':'根拠','Readiness':'購入準備','Score':'スコア','Best offer':'最安オファー','Warnings':'注意事項','Purchase readiness':'購入準備状況','IGI evidence':'IGIの根拠','Exact-stone market coverage':'同一石の市場調査','Structured optical review':'光学レビュー','All configured vendor checks':'設定済み販売店の確認','Matched retailer offers':'一致した販売店オファー','Reasons in favor':'評価できる点','Deductions and open questions':'減点と未確認事項','No recorded warnings':'記録された注意事項なし','None recorded':'記録なし','retailer listing':'販売店の商品ページ','image':'画像','source ↗':'情報源 ↗','table / depth':'テーブル / 深さ','NOT READY':'未準備','READY TO PURCHASE':'購入可能','READY FOR VENDOR QUESTIONS':'販売店への質問準備完了','READY FOR CHECKOUT VERIFICATION':'決済確認の準備完了','available':'在庫あり','fresh':'最新','missing':'未取得','validated':'検証済み','pending':'保留','priced':'価格あり','not_found':'見つからず','blocked':'アクセス不可','error':'エラー','unknown':'不明','outline':'輪郭','faceting':'ファセット','bow tie':'ボウタイ','central darkness':'中央の暗さ','tips':'先端','windowing':'ウィンドウイング','symmetry':'対称性','tilt performance':'傾斜時の見え方'}};
const originals=new WeakMap();function translateNode(n,lang){{if(!originals.has(n))originals.set(n,n.nodeValue);const raw=originals.get(n),trim=raw.trim(),value=translations[trim];n.nodeValue=lang==='ja'&&value?raw.replace(trim,value):raw}}function setLanguage(lang){{document.documentElement.lang=lang;const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;while(n=walker.nextNode()){{if(!['SCRIPT','STYLE'].includes(n.parentElement.tagName))translateNode(n,lang)}}document.querySelector('#language').value=lang;localStorage.setItem('diamond-finder-language',lang)}}const language=document.querySelector('#language');language.addEventListener('change',()=>setLanguage(language.value));setLanguage(localStorage.getItem('diamond-finder-language')||'en');
Object.assign(translations,{{'Diamond Finder · your shortlist, made clearer':'Diamond Finder · 候補をもっとわかりやすく','Find the diamond that feels right':'心から選びたいと思えるダイヤモンドを','Compare your strongest matches, see the best available prices, and know what still needs checking before you buy.':'有力候補と最安価格を比べ、購入前に確認すべきことをひと目で把握できます。','Best match right now':'現在のベストマッチ','Diamonds compared':'比較したダイヤモンド','Ready to buy':'購入準備完了','IGI reports verified':'検証済みIGIレポート','How we picked the best matches':'候補を選んだ基準','Show me':'表示順','best matches first':'おすすめ順','lowest prices first':'価格の安い順','closest size first':'目標サイズに近い順','highest match scores first':'マッチスコアの高い順','Pick':'順位','IGI report':'IGIレポート','Shape details':'形状の詳細','What we checked':'確認状況','Next step':'次のステップ','Match':'マッチ度','Best price':'最安価格','Worth knowing':'確認ポイント'}});
Object.assign(translations,{{
'Start here if you want to understand the recommendations. The detailed math is available, but you do not need it to compare the stones.':'おすすめの理由を知りたい方はこちらをご覧ください。詳しい計算方法も確認できますが、候補の比較に数式の理解は必要ありません。',
'First, the essentials':'まず、外せない条件','Only D/E color, VS1 or better, Excellent polish and symmetry, and the correct IGI cutting style make the list.':'D/Eカラー、VS1以上、研磨と対称性がExcellent、そして正しいIGIカットスタイルの石だけを候補にしています。',
'Then, the right size':'次に、理想のサイズ','Stones closest to your 15.5 × 7.8 mm target rank higher. Width matters a little more because it has a strong effect on the face-up look.':'目標の15.5 × 7.8 mmに近い石ほど高く評価しています。正面から見た印象に大きく影響するため、幅をやや重視しています。',
'Your preferred shape':'お好みのプロポーション','A 1.90–2.05 ratio, 55–65% table, and 58–67% depth are preferred. A small miss lowers the match score; it does not automatically rule a stone out.':'縦横比1.90〜2.05、テーブル55〜65%、深さ58〜67%が理想です。わずかに外れても評価が少し下がるだけで、候補から自動的に除外されることはありません。',
'Confidence matters':'安心できる根拠','A verified IGI report and stone-specific photos or video make a recommendation more trustworthy. Retailer descriptions alone are not enough.':'検証済みのIGIレポートと、その石専用の写真や動画があるほど安心して判断できます。販売店の説明だけでは十分ではありません。',
'Diamond score':'マッチスコア','This is the overall match for your size, proportions, and available evidence. Higher is better, and price is deliberately left out.':'希望するサイズやプロポーションとの一致度、確認できた資料を総合した評価です。数値が高いほど好条件で、価格は含みません。',
'Value score':'価格を含めた評価','This adds price to the picture, helping you spot a strong match at a competitive price. Any promotion should still be confirmed at checkout.':'価格も含めて、お買い得な有力候補を見つけるための評価です。割引は購入手続き時に必ずご確認ください。',
'One important note:':'大切なポイント：','Neither score predicts brilliance or how the diamond will look in person. Photos, video, and a careful visual review are still essential.':'どちらのスコアも、輝きや実物の見え方を保証するものではありません。写真や動画を使った丁寧な確認が欠かせません。',
'Before you buy':'購入前のチェック','The score is a comparison tool, not a beauty grade. Use it to narrow the list, then review the actual stone.':'スコアは候補を比べるための目安で、美しさの等級ではありません。候補を絞った後は、実際の石を写真や動画でご確認ください。',
'IGI report':'IGIレポート','Verification:':'検証状況：','Saved file:':'保存ファイル：','Last checked:':'最終確認：','Where we looked':'販売店の調査状況','How it looks':'見た目の確認','These observations come from the available photos and video.':'以下は、確認できる写真と動画に基づく所見です。','Retailers checked':'確認した販売店','Available offers':'購入できる販売店','Nothing to flag':'特に気になる点はありません','View IGI report ↗':'IGIレポートを見る ↗','View at retailer':'販売店で見る','360° video':'360°動画','image':'画像','Retailer price:':'販売価格：','Price checked':'価格確認日','What stands out':'良いポイント','What to check next':'次に確認すること','See the calculation':'計算方法を見る','Nothing else to check right now':'現時点で追加の確認事項はありません','Use this shortlist as a confident starting point, not the final word. Before buying, confirm the IGI report and laser inscription, watch the stone-specific video, check the final checkout price and availability, and review the seller\'s return policy.':'この候補一覧は、安心して選び始めるための出発点です。購入前にIGIレポートとレーザー刻印、その石専用の動画、最終価格と在庫、販売店の返品条件をご確認ください。'
}});
translateNode=function(n,lang){{if(!originals.has(n))originals.set(n,n.nodeValue);const raw=originals.get(n),trim=raw.trim();if(lang!=='ja'){{n.nodeValue=raw;return}}let value=translations[trim];if(value){{n.nodeValue=raw.replace(trim,value);return}}value=raw.replace(/From (\$[\d,.]+) at ([^·]+) · READY FOR VENDOR QUESTIONS/g,'$2で$1から · 販売店への確認が必要').replace(/From (\$[\d,.]+) at ([^·]+) · NOT READY/g,'$2で$1から · 購入前の確認が必要').replace(/From (\$[\d,.]+) at ([^·]+) · READY TO PURCHASE/g,'$2で$1から · 購入準備完了').replace(/See why this stone ranked here and compare (\d+) offers/g,'この順位の理由と$1件の販売情報を見る').replace(/We searched (\d+) of (\d+) retailers using this exact IGI number\./g,'このIGI番号で$2店中$1店を検索しました。').replace(/(\d+) offers found · (\d+) recent prices · (\d+) stock confirmations · (\d+) checkout prices verified\./g,'販売情報 $1件 · 最新価格 $2件 · 在庫確認 $3件 · 購入画面での価格確認 $4件').replace(/(\d+) retailers had no match · (\d+) older listings found\./g,'該当なし $1店 · 過去の掲載 $2件').replace(/Price checked ([\d-]+)/g,'価格確認日 $1').replace(/Retailer price: /g,'販売価格：').replace(/available · fresh \((\d+) days\)/g,'在庫あり · $1日前に確認').replace(/IGI validated/g,'IGI 検証済み').replace(/IGI missing/g,'IGI 未検証').replace(/Optical pending/g,'見た目の確認待ち').replace(/Match score · value/g,'マッチスコア · 価格評価').replace(/table \/ depth/g,'テーブル / 深さ').replace(/ ratio /g,' 縦横比 ');n.nodeValue=value}};
Object.assign(translations,{{'Nothing to flag':'特に気になる点はありません','The photos and video still need a closer look':'写真と動画をもう一度詳しく確認する必要があります','The saved IGI report still needs to be verified':'保存したIGIレポートは未検証です','No 360° video is available for this stone yet':'この石専用の360°動画はまだありません','No retailer has recently confirmed that it is in stock':'最近在庫を確認できた販売店がありません','Return and buyer-protection terms still need review':'返品条件と購入者保護の確認が必要です','One or more proportions sit outside your preferred range':'一部のプロポーションが希望範囲から外れています','Some supporting evidence is still missing':'確認資料が一部不足しています'}});
Object.assign(translations,{{'highest prices first':'価格の高い順'}});
Object.assign(translations,{{'See the actual stone':'実際のダイヤモンドを見る','Stone-specific view':'この石の実物画像','This is the retailer image for this exact IGI number.':'このIGI番号の石について販売店が掲載している画像です。','View interactive 360° ↗':'360°ビューを見る ↗','360° rotation not supplied by the retailer':'販売店から360°ビューは提供されていません','No stone-specific image or 360° view is available yet.':'この石専用の画像や360°ビューはまだありません。'}});
Object.assign(translations,{{'USD':'JPY'}});
const usdJpyRate=157.98,languageSetText=setLanguage;setLanguage=function(lang){{languageSetText(lang);document.querySelectorAll('.money').forEach(el=>{{const usd=Number(el.dataset.usd);el.textContent=lang==='ja'?new Intl.NumberFormat('ja-JP',{{style:'currency',currency:'JPY',maximumFractionDigits:0}}).format(Math.round(usd*usdJpyRate)):new Intl.NumberFormat('en-US',{{style:'currency',currency:'USD'}}).format(usd);el.title=lang==='ja'?`US $${{usd.toLocaleString('en-US',{{minimumFractionDigits:2,maximumFractionDigits:2}})}}`:''}});const note=document.querySelector('#fx-note');note.hidden=lang!=='ja';note.textContent=lang==='ja'?'参考換算：1米ドル＝157.98円（2026年10月15日）。実際の請求額は決済時の為替レートにより異なります。':''}};
const translateWithStoneSummary=translateNode;translateNode=function(n,lang){{translateWithStoneSummary(n,lang);if(lang==='ja')n.nodeValue=n.nodeValue.replace(/View this stone and compare (\d+) offers/g,'このダイヤモンドと$1件の販売情報を見る')}};
setLanguage(localStorage.getItem('diamond-finder-language')||'en');
</script></body></html>'''


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--input', default='dashboard_data.json'); parser.add_argument('--output', default='diamond_report.html'); args = parser.parse_args()
    data = read_json(REPORTS / args.input); (REPORTS / args.output).write_text(render(data), encoding='utf-8')
    print(f'Wrote styled report to reports/{args.output}')


if __name__ == '__main__': main()
