"""Target specs and cut-label rules. Retailer 'hexagonal' is not Dutch confirmation."""
from __future__ import annotations

import re

from pricing import numeric_price

TARGET_LENGTH = 15.5
TARGET_WIDTH = 7.8
RATIO_RANGE = (1.90, 2.05)
DEPTH_RANGE = (58.0, 67.0)
TABLE_RANGE = (55.0, 65.0)
DIMENSION_TOLERANCE = (0.50, 0.25)
COLORS = {'D', 'E'}
CLARITIES = {'VS1', 'VVS2', 'VVS1', 'IF', 'FL'}
FINISH_OK = {'excellent', 'ex'}


def numeric(value):
    return numeric_price(value)


def in_range(value, bounds) -> bool:
    return value is not None and bounds[0] <= value <= bounds[1]


def dimension_score(length, width) -> str:
    if length is None or width is None:
        return ''
    return f'{((length - TARGET_LENGTH) / 0.35) ** 2 + ((width - TARGET_WIDTH) / 0.2) ** 2:.3f}'


def preference_flags(row: dict) -> list[str]:
    """Soft warnings. They screen and explain; they do not automatically reject."""
    length, width = numeric(row.get('length_mm')), numeric(row.get('width_mm'))
    ratio = numeric(row.get('ratio')) or (length / width if length and width else None)
    depth, table = numeric(row.get('depth_pct')), numeric(row.get('table_pct'))
    flags = []
    if length is not None and abs(length - TARGET_LENGTH) > DIMENSION_TOLERANCE[0]:
        flags.append(f'length {length:g} mm differs from target {TARGET_LENGTH:g} mm')
    if width is not None and abs(width - TARGET_WIDTH) > DIMENSION_TOLERANCE[1]:
        flags.append(f'width {width:g} mm differs from target {TARGET_WIDTH:g} mm')
    if ratio is not None and not in_range(ratio, RATIO_RANGE):
        flags.append(f'ratio {ratio:.3f} outside preferred {RATIO_RANGE[0]:.2f}-{RATIO_RANGE[1]:.2f}')
    if table is not None and not in_range(table, TABLE_RANGE):
        flags.append(f'table {table:g}% outside preferred {TABLE_RANGE[0]:g}-{TABLE_RANGE[1]:g}%')
    if depth is not None and not in_range(depth, DEPTH_RANGE):
        flags.append(f'depth {depth:g}% outside preferred {DEPTH_RANGE[0]:g}-{DEPTH_RANGE[1]:g}%')
    return flags


def ranking_components(row: dict) -> dict:
    """Return an intuitive 0-100 preference score; it is not an optical grade."""
    length, width = numeric(row.get('length_mm')), numeric(row.get('width_mm'))
    if length is None or width is None:
        return {'dimension_fit': None, 'preference_penalty': None, 'evidence_penalty': None,
                'value_component': None, 'overall': None}
    ratio = numeric(row.get('ratio')) or length / width
    depth, table = numeric(row.get('depth_pct')), numeric(row.get('table_pct'))
    price = numeric(row.get('effective_price_usd') or row.get('price_usd'))
    dimension = float(dimension_score(length, width))
    preference = 0.0
    if ratio < RATIO_RANGE[0]: preference += (RATIO_RANGE[0] - ratio) / 0.01 * 0.25
    elif ratio > RATIO_RANGE[1]: preference += (ratio - RATIO_RANGE[1]) / 0.01 * 0.25
    if depth is not None:
        if depth < DEPTH_RANGE[0]: preference += (DEPTH_RANGE[0] - depth) / 0.2
        elif depth > DEPTH_RANGE[1]: preference += (depth - DEPTH_RANGE[1]) / 0.2
    if table is not None:
        if table < TABLE_RANGE[0]: preference += (TABLE_RANGE[0] - table) / 0.5
        elif table > TABLE_RANGE[1]: preference += (table - TABLE_RANGE[1]) / 0.5
    cut_status = str(row.get('cutting_style_status') or '').lower()
    visual_status = str(row.get('visual_review_status') or '').lower()
    evidence = 0.0 if cut_status == 'verified_igi' else 5.0
    evidence += 0.0 if visual_status == 'reviewed' else 1.0 if 'pending' in visual_status else 3.0
    value = price / 4000.0 if price is not None else 1.0
    diamond_penalty = dimension + preference + evidence
    value_penalty = diamond_penalty + value
    return {
        'dimension_fit': round(max(0.0, 100.0 - dimension * 10.0), 1),
        'dimension_penalty': round(dimension, 3),
        'preference_penalty': round(preference, 3),
        'evidence_penalty': round(evidence, 3),
        'value_component': round(value, 3),
        'overall': round(max(0.0, 100.0 - diamond_penalty * 5.0), 1),
        'value_score': round(max(0.0, 100.0 - value_penalty * 5.0), 1),
    }


def quality_status(row: dict) -> str:
    length, width = numeric(row.get('length_mm')), numeric(row.get('width_mm'))
    ratio = numeric(row.get('ratio')) or (length / width if length and width else None)
    depth = numeric(row.get('depth_pct'))
    table = numeric(row.get('table_pct'))
    color = str(row.get('color') or '').upper()
    clarity = str(row.get('clarity') or '').upper()
    polish = str(row.get('polish') or '').lower()
    symmetry = str(row.get('symmetry') or '').lower()
    quality = all((
        length is not None,
        width is not None,
        color in COLORS,
        clarity in CLARITIES,
        polish in FINISH_OK,
        symmetry in FINISH_OK,
    ))
    missing = length is None or width is None or depth is None or table is None or not polish or not symmetry
    basic = all((
        length is not None,
        width is not None,
        color in COLORS,
        clarity in CLARITIES,
    ))
    if quality:
        flags = preference_flags(row)
        return 'PASS with preference flags: ' + '; '.join(flags) if flags else 'PASS numerical criteria'
    if missing and basic:
        return 'PENDING missing specifications'
    if length is None or width is None:
        return 'UNKNOWN (missing dimensions)'
    return 'OUTSIDE criteria'


def _blob(row: dict) -> str:
    return ' '.join(str(row.get(k) or '') for k in ('shape', 'title', 'shape_verified', 'shape_status'))


def is_step_cut(row: dict) -> bool:
    return bool(re.search(r'hexagonal\s+modified\s+step\s+cut', _blob(row), re.I)) or str(row.get('shape') or '').upper().startswith('EXCLUDED')


def is_modified_brilliant(row: dict) -> bool:
    return bool(re.search(r'hexagonal\s+modified\s+brilliant', _blob(row), re.I))


def is_hexagonal_label(row: dict) -> bool:
    return bool(re.search(r'hexagonal', _blob(row), re.I))


def shape_status(row: dict) -> str:
    retailer = str(row.get('retailer') or '')
    shape = str(row.get('shape') or '')
    title = str(row.get('title') or '')
    if is_step_cut(row):
        return 'EXCLUDED - Cut'
    if retailer == 'Calavera' and shape.lower() == 'square radiant':
        return 'EXCLUDED - Square Radiant'
    if retailer == 'Aurelinne' and shape.upper() == 'MARQUISE':
        return 'REGULAR MARQUISE (excluded from Dutch shortlist)'
    if is_modified_brilliant(row):
        return 'HEXAGONAL MODIFIED BRILLIANT (accept; inspect facets)'
    if is_hexagonal_label(row):
        return 'HEXAGONAL LABEL (facet style unverified)'
    if retailer == 'Stienhardt' or (retailer == 'Loose Grown Diamond' and 'dutch' in shape.lower()):
        return 'DUTCH MARQUISE LABEL (verify photo/report)' if retailer != 'Stienhardt' else 'DUTCH MARQUISE LABEL (verify photo)'
    if 'dutch' in (shape + ' ' + title).lower():
        return 'DUTCH MARQUISE LABEL (verify photo/report)'
    return 'OTHER/UNKNOWN (inspect photo/report)'


def facet_verification(row: dict) -> str:
    note = str(row.get('source_note') or '')
    if is_step_cut(row):
        return 'Rejected: Hexagonal Modified Step Cut'
    if is_modified_brilliant(row):
        if 'IGI' in note.upper() or 'report' in note.lower():
            return 'Labeled Hexagonal Modified Brilliant; inspect facets (not assumed from hexagonal alone)'
        return 'Labeled Hexagonal Modified Brilliant; inspect IGI and video'
    if is_hexagonal_label(row):
        return 'Unverified hexagonal label; inspect IGI facet style'
    return 'Unverified; inspect IGI and video'


def dutch_shortlist_candidate(row: dict) -> bool:
    if is_step_cut(row):
        return False
    retailer = str(row.get('retailer') or '')
    shape = str(row.get('shape') or '').upper()
    if retailer == 'Stienhardt':
        return True
    if retailer == 'Aurelinne' and shape == 'MARQUISE':
        return False
    if shape in {'MARQUISE', 'ROUND', 'OVAL', 'SQUARE RADIANT'} or shape.startswith('EXCLUDED'):
        return False
    if retailer == 'Mikado Diamonds':
        length, width = numeric(row.get('length_mm')), numeric(row.get('width_mm'))
        color = str(row.get('color') or '').upper()
        return (
            length is not None and 14.5 <= length <= 16.5
            and width is not None and 7.2 <= width <= 8.4
            and color in COLORS
        )
    return retailer in {'Aurelinne', 'Calavera', 'Loose Grown Diamond', 'Mikado Diamonds'}
