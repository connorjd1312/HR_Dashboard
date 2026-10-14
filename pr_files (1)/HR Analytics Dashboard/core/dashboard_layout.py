from __future__ import annotations

from core import analytics

MAX_CHARTS = 4


def reorder(items: list, item, index: int) -> list:
    # index is a position in the original list; len(items) means the end.
    if item not in items:
        return list(items)
    old = items.index(item)
    index = max(0, min(index, len(items)))
    out = list(items)
    out.pop(old)
    if old < index:
        index -= 1
    out.insert(index, item)
    return out


def swap(items: list, a: int, b: int) -> list:
    out = list(items)
    if 0 <= a < len(out) and 0 <= b < len(out):
        out[a], out[b] = out[b], out[a]
    return out


def insertion_index(centres: list[float], x: float) -> int:
    return sum(1 for c in centres if c < x)


def default_layout() -> dict:
    return {
        'kpis': list(analytics.DEFAULT_KPIS),
        'multi_mode': False,
        'charts': [{'metric': 'Total Employees', 'dimension': 'Department', 'chart_type': 'Auto'}],
    }


def sanitize_layout(state) -> dict:
    base = default_layout()
    if not isinstance(state, dict):
        return base

    kpis = state.get('kpis')
    if isinstance(kpis, list):
        seen = []
        for m in kpis:
            m = analytics.canonical_metric(m) if isinstance(m, str) else m
            if m in analytics.KPI_OPTIONS and m not in seen:
                seen.append(m)
        base['kpis'] = seen

    charts = []
    raw = state.get('charts')
    if isinstance(raw, list):
        for cfg in raw:
            if len(charts) >= MAX_CHARTS:
                break
            if not isinstance(cfg, dict):
                continue
            metric = analytics.canonical_metric(cfg.get('metric', ''))
            dim = cfg.get('dimension')
            ctype = cfg.get('chart_type')
            if metric not in analytics.SNAPSHOT_METRICS or dim not in analytics.GROUP_BY_OPTIONS:
                continue
            charts.append({'metric': metric, 'dimension': dim,
                           'chart_type': ctype if ctype in analytics.CHART_TYPES else 'Auto'})
    if charts:
        base['charts'] = charts
    base['multi_mode'] = bool(state.get('multi_mode')) and bool(charts)
    return base
