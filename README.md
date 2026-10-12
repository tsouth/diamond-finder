# Diamond Finder

Evidence-first discovery, deduplication, ranking, and purchase validation for lab-grown Dutch marquise diamonds.

## What the system proves—and what it does not

Diamond Finder keeps physical diamonds separate from retailer offers and identifies stones primarily by normalized IGI report number. Retailer labels such as “hexagonal,” “Dutch marquise,” and “marquise” are not accepted as proof of cutting style.

The diamond score measures dimensional fit, stated preferences, and evidence gaps. A separate value score adds price influence, while the offer comparison independently identifies the cheapest retailer. Neither score is an optical-performance grade, and a stone cannot become purchase-ready merely because it ranks first.

## Workflow

1. Collect retailer inventory from Stienhardt, Aurélinne, Calavera, and Mikado.
2. Add manually confirmed or exact-certificate offers, including Ritani.
3. Normalize identities and attach every offer to one physical diamond.
4. Validate a retained IGI report and require `HEXAGONAL MODIFIED BRILLIANT`.
5. Reject `HEXAGONAL MODIFIED STEP CUT` and flag retailer/report contradictions.
6. Complete a structured review of stone-specific imagery.
7. Track offer freshness, live availability, promotion status, retailer coverage, and buyer-protection terms.
8. Produce a purchase-readiness status with explicit blockers.

## Commands

```powershell
py -m pip install -r requirements.txt
py run_all.py                  # live collection and complete report pipeline
py run_all.py --offline        # rebuild from saved inventory and evidence
py -m pytest -q -p no:cacheprovider
```

Open [reports/diamond_report.html](reports/diamond_report.html) for the purchase-confidence dashboard.

Every full live run attempts an exact-certificate lookup for every shortlisted stone across all 11 configured retailers. Each retailer returns a row with `priced`, `found_no_price`, `not_found`, `blocked`, `unresolved`, or `error`; the system never invents a price when a retailer does not expose one. `reports/vendor_price_checks.csv` contains the complete matrix. Offline runs explicitly mark vendors that were not contacted.

## IGI report acquisition

IGI retrieval is intentionally layered because its public site is not consistently automation-friendly:

```powershell
# Try official direct PDF locations
py igi_report.py LG825678759

# Also try the public verification page through installed Microsoft Edge
py igi_report.py LG825678759 --playwright

# Guaranteed fallback after downloading the PDF in a normal browser
py igi_report.py LG825678759 --import-pdf "C:\path\to\report.pdf"
```

The tool stores the original PDF, SHA-256 digest, source, retrieval time, extracted fields, and validation result under `data/evidence/certificates/`. It checks the report number, cutting style, measurements, carat, color, clarity, polish, and symmetry against the expected diamond. Browser automation follows the normal public lookup flow; it does not bypass CAPTCHAs or access controls.

Manual import is a supported first-class workflow, not a failure mode. A retained, hash-identified PDF is more auditable than a transient browser page.

## Optical review

Edit `config/optical_reviews.json` after examining the entire stone-specific rotation. A completed review requires observations for:

- outline;
- faceting;
- bow tie;
- central darkness;
- tip activity;
- windowing;
- symmetry;
- tilt performance.

Record reviewer, date, confidence, lighting, source URLs, frame evidence, and notes. Studio imagery alone should normally remain pending until neutral-light video is available.

## Readiness states

- `NOT READY`
- `READY FOR VENDOR QUESTIONS`
- `READY FOR CHECKOUT VERIFICATION`
- `READY TO PURCHASE`

Readiness requires certificate validation, completed optical review, a fresh explicitly available offer, and recorded seller protections. `READY TO PURCHASE` additionally requires a verified checkout observation.

## Project layout

```text
config/                       Curated evidence, coverage, reviews, and policies
data/current/                 Latest normalized retailer exports
data/raw/<retailer>/          Untouched collector responses
data/evidence/certificates/   Validation metadata (original PDFs remain private)
data/evidence/optical/        Captured optical evidence
data/reference/               Stable historical fixtures
data/runs/<timestamp>/        Local immutable pipeline snapshots (not published)
reports/                      Current CSV, JSON, coverage, and HTML outputs
tests/                        Regression and confidence-gate tests
archive/                      Retired integrations retained for auditability
```

## Selection preferences

- Target dimensions: approximately 15.5 × 7.8 mm
- Length/width ratio: 1.90–2.05
- Color: D/E
- Clarity: VS1 or better
- Table: preferably 55–65%
- Depth: preferably 58–67%
- Polish and symmetry: Excellent

Dimension, table, and depth deviations generate warnings rather than automatic rejection. Actual facet pattern and optical behavior require stone-specific review.

Promotional prices—including `FALL10`—remain estimated until accepted at checkout. Prices and availability are timestamped observations, never guarantees.

## Heart Side-Stone Finder

Heart side stones use a completely separate criteria and pairing engine; their scores never affect the Dutch-marquise center ranking.

```powershell
py heart_side_stones.py
```

Inventory belongs in `data/current/heart_side_stones.csv`. Outputs include `reports/heart_side_stone_report.html`, ranked pair CSV/JSON, and subtle/balanced/bold SVG layouts drawn in physical millimeter units for center diamond LG825678759. Print SVG/HTML layouts at 100% only after checking the included millimeter ruler. The renderings model face-up outline and spacing, not pavilion depth, setting tilt, prongs, or optical performance.

The initial heart screen follows IGI's published Heart Brilliant Excellent-candidate ranges: L/W 0.85–0.95, total depth 51.9–61%, table 58–64%, and Very Good/Excellent polish and symmetry. Proportions are only a screening gate; a defined cleft, matched lobes and wings, point integrity, bow tie, and light behavior still require imagery review.
