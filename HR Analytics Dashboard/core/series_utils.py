from __future__ import annotations

import uuid

import pandas as pd

PALETTE = [
    '#1F3864', '#2E75B6', '#1E8449', '#C0392B',
    '#D4AC0D', '#5B2C6F', '#117A65', '#E67E22',
]


def iso(d) -> str:
    return pd.Timestamp(d).strftime('%Y-%m-%d')


def date_range(months, df) -> tuple[str, str]:
    end = pd.Timestamp.today().normalize()
    if months is None:
        start = df['Hire_Date'].min() if df is not None and len(df) else end - pd.DateOffset(years=5)
    else:
        start = end - pd.DateOffset(months=months)
    return iso(start), iso(end)


def auto_granularity(start_iso: str, end_iso: str) -> str:
    days = (pd.Timestamp(end_iso) - pd.Timestamp(start_iso)).days
    if days <= 100:
        return 'Weekly'
    if days <= 760:
        return 'Monthly'
    return 'Quarterly'


def auto_label(s: dict) -> str:
    if s['view_type'] == 'snapshot':
        return f"{s['metric']} by {s['group_by']}"
    parts = [s['metric']]
    if s.get('filter_val') not in (None, 'All'):
        parts.append(s['filter_val'])
    return ' · '.join(parts)


def make_series(view_type: str, metric: str, *, style: str, color: str,
                group_by: str | None = None, filter_by: str = 'None',
                filter_val: str = 'All', start_date: str | None = None,
                end_date: str | None = None, granularity: str | None = None,
                show_trend: bool = False, label: str | None = None) -> dict:
    s = {
        'id': str(uuid.uuid4())[:8], 'view_type': view_type, 'metric': metric,
        'filter_by': filter_by, 'filter_val': filter_val,
        'start_date': start_date, 'end_date': end_date, 'granularity': granularity,
        'style': style, 'show_trend': show_trend, 'color': color, 'group_by': group_by,
    }
    s['label'] = label or auto_label(s)
    return s
