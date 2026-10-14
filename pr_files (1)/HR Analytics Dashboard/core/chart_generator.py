# Interprets a plain-English chart request with the local model when available, otherwise by keywords.
# Either result is validated so only charts the Analytics Builder can draw are returned.

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import pandas as pd

from core import analytics
from core.local_llm_client import LocalLLMError
from core.series_utils import PALETTE, auto_granularity, date_range, iso, make_series

TIME_STYLES = ['Line', 'Bar', 'Area', 'Scatter']
SNAP_STYLES = ['Vertical Bar', 'Horizontal Bar', 'Scatter', 'Pie']
MAX_SERIES = 8
MAX_TOKENS = 450
_MANY_GROUPS = 6

_TIME_TO_SNAP = {
    'Turnover Rate per Period (%)': 'Overall Turnover Rate (%)',
    'Attrition (Voluntary Leavers) Rate per Period (%)': 'Attrition (Voluntary Leavers) Rate (%)',
}
_SNAP_TO_TIME = {v: k for k, v in _TIME_TO_SNAP.items()}


@dataclass
class ChartSuggestion:
    title: str
    series: list[dict]
    engine: str
    notes: list[str] = field(default_factory=list)

    def describe(self) -> str:
        lines = []
        for s in self.series:
            if s['view_type'] == 'time':
                who = '' if s.get('filter_val') in (None, 'All') else f" for {s['filter_val']}"
                lines.append(
                    f"{s['metric']}{who} over time: {analytics.format_period(s['start_date'], s['end_date'])}, "
                    f"{(s.get('granularity') or 'Monthly').lower()}, {s['style'].lower()}"
                    + (', with trend line' if s.get('show_trend') else ''))
            else:
                lines.append(f"{s['metric']} by {s['group_by']}: {s['style'].lower()}")
        return '\n'.join(lines)


class ChartRequestError(ValueError):
    pass


def _col(dim: str) -> str:
    return analytics._COL_MAP.get(dim, dim)


def _match_value(df: pd.DataFrame, dim: str, value) -> str | None:
    col = _col(dim)
    if df is None or col not in df.columns or value is None:
        return None
    wanted = str(value).strip().lower()
    for v in df[col].dropna().unique():
        if str(v).lower() == wanted:
            return str(v)
    return None


def _pick_months(spec) -> int | None:
    m = spec.get('months')
    if m in (None, 0, '0', 'all', 'All'):
        return None
    try:
        return max(1, min(120, int(m)))
    except (TypeError, ValueError):
        return 12


def normalise_spec(spec: dict, df: pd.DataFrame, notes: list[str]) -> dict | None:
    if not isinstance(spec, dict):
        return None
    metric = analytics.canonical_metric(str(spec.get('metric', '')).strip())
    view = str(spec.get('view', '')).strip().lower()
    if view not in ('time', 'snapshot'):
        view = 'time' if metric in analytics.TIME_SERIES_METRICS else 'snapshot'

    if view == 'time' and metric not in analytics.TIME_SERIES_METRICS:
        if metric in _SNAP_TO_TIME:
            metric = _SNAP_TO_TIME[metric]
        else:
            notes.append(f'"{metric}" can only be shown by group, not over time, so it is shown by group.')
            view = 'snapshot'
    if view == 'snapshot' and metric not in analytics.SNAPSHOT_METRICS:
        if metric in _TIME_TO_SNAP:
            metric = _TIME_TO_SNAP[metric]
        elif metric in analytics.TIME_SERIES_METRICS:
            notes.append(f'{metric} can only be shown over time, not by group.')
            view = 'time'
        else:
            return None
    if view == 'time' and metric not in analytics.TIME_SERIES_METRICS:
        return None

    out = {'view': view, 'metric': metric}
    if view == 'time':
        by = spec.get('filter_by')
        val = spec.get('filter_val')
        out['filter_by'], out['filter_val'] = 'None', 'All'
        if by in analytics.GROUP_BY_OPTIONS and val not in (None, '', 'All'):
            real = _match_value(df, by, val)
            if real is not None:
                out['filter_by'], out['filter_val'] = by, real
            else:
                notes.append(f'There is no {by} called "{val}" in the data, so all employees are shown.')
        if spec.get('start'):
            try:
                out['start'] = iso(spec['start'])
                out['end'] = iso(spec['end']) if spec.get('end') else iso(pd.Timestamp.today())
            except (ValueError, TypeError):
                out['months'] = _pick_months(spec)
        else:
            out['months'] = _pick_months(spec)
        gran = spec.get('granularity')
        out['granularity'] = gran if gran in analytics.GRANULARITIES else None
        style = spec.get('style')
        out['style'] = style if style in TIME_STYLES else 'Line'
        out['trend'] = bool(spec.get('trend'))
    else:
        group = spec.get('group_by')
        out['group_by'] = group if group in analytics.GROUP_BY_OPTIONS else 'Department'
        style = spec.get('style')
        if style in ('Donut', 'Doughnut'):
            style = 'Pie'
        out['style'] = style if style in SNAP_STYLES else None
        if out['style'] == 'Pie' and metric not in analytics.PARTS_OF_WHOLE_METRICS:
            notes.append('A pie chart only makes sense for headcounts, so bars are used instead.')
            out['style'] = None
    return out


def build_suggestion(specs: list, df: pd.DataFrame, title: str | None, engine: str,
                     notes: list[str] | None = None) -> ChartSuggestion:
    notes = list(notes or [])
    valid = []
    for spec in specs or []:
        n = normalise_spec(spec, df, notes)
        if n is not None:
            valid.append(n)
    if not valid:
        raise ChartRequestError(
            "I couldn't tell what to chart. Try naming a measure, for example: "
            '"turnover by department", "hires vs departures last 12 months" or '
            '"average salary by job role as a bar chart".')

    kind = valid[0]['view']
    if any(v['view'] != kind for v in valid):
        notes.append('Over-time and by-group measures can\'t share a chart, so only the first kind is used.')
        valid = [v for v in valid if v['view'] == kind]
    if len(valid) > MAX_SERIES:
        notes.append(f'Showing the first {MAX_SERIES} series.')
        valid = valid[:MAX_SERIES]

    series = []
    for i, v in enumerate(valid):
        color = PALETTE[i % len(PALETTE)]
        if kind == 'time':
            if v.get('start'):
                start, end = v['start'], v['end']
            else:
                start, end = date_range(v['months'], df)
            series.append(make_series(
                'time', v['metric'], style=v['style'], color=color,
                filter_by=v['filter_by'], filter_val=v['filter_val'],
                start_date=start, end_date=end,
                granularity=v['granularity'] or auto_granularity(start, end),
                show_trend=v['trend']))
        else:
            style = v['style']
            if style is None:
                n_groups = _group_count(df, v['group_by'])
                style = 'Horizontal Bar' if n_groups > _MANY_GROUPS else 'Vertical Bar'
            series.append(make_series('snapshot', v['metric'], style=style, color=color,
                                      group_by=v['group_by']))

    return ChartSuggestion(title or _auto_title(series), series, engine, notes)


def _group_count(df, dim) -> int:
    col = _col(dim)
    return int(df[col].nunique()) if df is not None and col in df.columns else 0


def _auto_title(series: list[dict]) -> str:
    if len(series) == 1:
        return series[0]['label']
    metrics = list(dict.fromkeys(s['metric'] for s in series))
    if series[0]['view_type'] == 'snapshot':
        return ' vs '.join(metrics) + f" by {series[0]['group_by']}"
    if len(metrics) > 1:
        return ' vs '.join(metrics)
    by = series[0].get('filter_by')
    return f'{metrics[0]} by {by}' if by and by != 'None' else metrics[0]


_WORD_NUMBERS = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
                 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'twelve': 12, 'eighteen': 18}

_METRIC_PATTERNS = [
    ('hires', r'\b(hires?|hired|hiring|recruit\w*|joiners?|new starters?|onboard\w*)\b'),
    ('departures', r'\b(departures?|leavers?|exits?|left|leaving|quit|separations?)\b'),
    ('attrition', r'\b(attrition|voluntary|resign\w*|retire\w*)\b'),
    ('turnover', r'\b(turnover|churn)\b'),
    ('salary', r'\b(salar(y|ies)|pay|wages?|compensation|earn\w*)\b'),
    ('tenure', r'\b(tenure|length of service|years of service|seniority)\b'),
    ('age', r'\b(ages?|how old)\b'),
    ('absence', r'\b(absen\w*|sick(ness)?|days off)\b'),
    ('leave', r'\b(leave balance|annual leave|leave days|days of leave|remaining leave|holidays?)\b'),
]
_HEADCOUNT_STRONG = r'\b(head ?count|number of (employees|people|staff)|(employee|staff) count|total employees|how many)\b'
_HEADCOUNT_WEAK = r'\b(employees|staff|people|workforce|count)\b'

_TIME_METRIC = {
    'hires': 'Hires', 'departures': 'Departures',
    'turnover': 'Turnover Rate per Period (%)',
    'attrition': 'Attrition (Voluntary Leavers) Rate per Period (%)',
}
_SNAP_METRIC = {
    'turnover': 'Overall Turnover Rate (%)',
    'attrition': 'Attrition (Voluntary Leavers) Rate (%)',
    'salary': 'Average Salary ($)', 'tenure': 'Average Tenure (yrs)', 'age': 'Average Age',
    'absence': 'Average Absenteeism (days)', 'leave': 'Average Leave Balance (days)',
    'headcount': 'Total Employees',
}

_DIM_PATTERNS = [
    ('Age Group', r'\bage[- ]?(groups?|bands?|brackets?|ranges?)\b|\b(by|per|across) ages?\b'),
    ('Department', r'\b(departments?|depts?|teams?|divisions?)\b'),
    ('Job Role', r'\b(job roles?|roles?|positions?|job titles?|titles?)\b'),
    ('Status', r'\b(employment status|status)\b'),
    ('Sex', r'\b(sex|gender)\b'),
    ('Ethnicity', r'\b(ethnicity|ethnic\w*|race)\b'),
]
_BY = r'(?:by|per|across|each|every|for each|between|split by|broken down by|grouped by|compare|comparing|versus|vs\.?)\s+(?:the\s+)?(?:each\s+)?'

_TIME_WORDS = (r'\b(over time|trends?|trending|monthly|weekly|quarterly|yearly|annual(ly)?|per (month|week|quarter|year)|'
               r'each (month|week|quarter|year)|history|historical|timeline|since|year to date|ytd|'
               r'(last|past|previous) (\d+|\w+ )?(weeks?|months?|quarters?|years?)|(by|per) (month|week|quarter|year))\b')

_VALUE_DIMS = ['Department', 'Job Role', 'Sex', 'Status', 'Ethnicity']
_SEX_WORDS = {'female': 'Female', 'women': 'Female', 'woman': 'Female',
              'male': 'Male', 'men': 'Male', 'man': 'Male'}
_STATUS_WORDS = {'active': 'Active', 'resigned': 'Resigned', 'terminated': 'Terminated',
                 'retired': 'Retired', 'on leave': 'On Leave'}


def _to_int(token: str | None, default: int = 1) -> int:
    if not token:
        return default
    token = token.strip().lower()
    return int(token) if token.isdigit() else _WORD_NUMBERS.get(token, default)


def _find_metrics(text: str) -> list[str]:
    scrubbed = re.sub(_DIM_PATTERNS[0][1], ' ', text)
    found = []
    for key, pat in _METRIC_PATTERNS:
        src = scrubbed if key == 'age' else text
        m = re.search(pat, src)
        if m:
            found.append((m.start(), key))
    keys = [k for _, k in sorted(found)]
    if re.search(_HEADCOUNT_STRONG, text) or (not keys and re.search(_HEADCOUNT_WEAK, text)):
        keys.append('headcount')
    return keys


def _find_dimension(text: str) -> tuple[str | None, bool]:
    for dim, pat in _DIM_PATTERNS:
        if re.search(_BY + r'(?:' + pat + r')', text):
            return dim, True
    for dim, pat in _DIM_PATTERNS:
        if re.search(pat, text):
            return dim, False
    return None, False


def _find_values(text: str, df: pd.DataFrame) -> dict[str, list[str]]:
    found: dict[str, list[tuple[int, str]]] = {}

    def add(dim, pos, val):
        found.setdefault(dim, [])
        if val not in [v for _, v in found[dim]]:
            found[dim].append((pos, val))

    for dim in _VALUE_DIMS:
        col = _col(dim)
        if df is None or col not in df.columns:
            continue
        for v in df[col].dropna().unique():
            v = str(v)
            if dim in ('Sex', 'Status'):
                continue
            m = re.search(r'(?<![\w])' + re.escape(v.lower()) + r's?(?![\w])', text)
            if m:
                add(dim, m.start(), v)
    if df is not None and 'Department' in df.columns and re.search(r'\bhr\b', text):
        real = _match_value(df, 'Department', 'Human Resources')
        if real:
            add('Department', text.index('hr'), real)
    if df is not None and 'Sex' in df.columns:
        for word, val in _SEX_WORDS.items():
            m = re.search(r'\b' + word + r'\b', text)
            if m and _match_value(df, 'Sex', val):
                add('Sex', m.start(), val)
    if df is not None and 'Status' in df.columns:
        for word, val in _STATUS_WORDS.items():
            m = re.search(r'\b' + word + r'\b', text)
            if m and _match_value(df, 'Status', val):
                add('Status', m.start(), val)
    # 'Sales Manager' contains 'Sales': keep the more specific role match.
    if 'Job Role' in found and 'Department' in found:
        role_spans = ' '.join(v.lower() for _, v in found['Job Role'])
        found['Department'] = [(p, v) for p, v in found['Department']
                               if not (v.lower() in role_spans and
                                       len(re.findall(r'\b' + re.escape(v.lower()) + r's?\b', text)) <= 1)]
        if not found['Department']:
            del found['Department']
    return {d: [v for _, v in sorted(vals)] for d, vals in found.items()}


def _find_time(text: str) -> dict:
    today = pd.Timestamp.today().normalize()
    if re.search(r'\b(all[- ]time|ever|entire history|full history|since the (start|beginning)|whole history)\b', text):
        return {'months': None}
    m = re.search(r'\b(?:in|during|for)\s+(?:the\s+year\s+)?(20\d\d|19\d\d)\b(?!\s*(?:months?|years?))', text)
    if m:
        y = int(m.group(1))
        return {'start': f'{y}-01-01', 'end': f'{y}-12-31'}
    m = re.search(r'\b(?:since|from)\s+(?:january\s+)?(20\d\d|19\d\d)\b', text)
    if m:
        return {'start': f'{int(m.group(1))}-01-01', 'end': iso(today)}
    if re.search(r'\b(this year|year to date|ytd)\b', text):
        return {'start': f'{today.year}-01-01', 'end': iso(today)}
    m = re.search(r'(?:last|past|previous|over|in|for)\s+(?:the\s+)?(?:last\s+|past\s+)?'
                  r'(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|twelve|eighteen)?\s*'
                  r'(week|month|quarter|year)s?\b', text)
    if m:
        n = _to_int(m.group(1))
        unit = m.group(2)
        months = {'week': max(1, round(n * 7 / 30)), 'month': n, 'quarter': n * 3, 'year': n * 12}[unit]
        return {'months': months, 'unit': unit}
    return {}


def _keyword_specs(text: str, df: pd.DataFrame, notes: list[str]) -> list[dict]:
    keys = _find_metrics(text)
    if not keys:
        raise ChartRequestError(
            "I couldn't find a measure in that. Try one of: headcount, hires, departures, turnover, "
            'attrition, salary, tenure, age, absenteeism or leave balance, for example '
            '"turnover by department" or "hires over the last 2 years".')

    when = _find_time(text)
    wants_time = bool(when) or bool(re.search(_TIME_WORDS, text))
    time_only = [k for k in keys if k in ('hires', 'departures')]
    has_time_variant = [k for k in keys if k in _TIME_METRIC]
    view = 'time' if (time_only or (wants_time and has_time_variant)) else 'snapshot'

    dim, explicit = _find_dimension(text)
    values = _find_values(text, df)

    if view == 'time':
        metrics = [_TIME_METRIC[k] for k in keys if k in _TIME_METRIC]
        dropped = [k for k in keys if k not in _TIME_METRIC]
        if dropped:
            notes.append('Left out ' + ', '.join(_SNAP_METRIC.get(k, k) for k in dropped)
                         + ' (it can\'t be shown over time).')
        base = {'view': 'time', 'trend': bool(re.search(r'trend ?line|with (a )?trend|regression|line of best fit', text))}
        base.update({k: v for k, v in when.items() if k in ('months', 'start', 'end')})
        if not when:
            base['months'] = 12
        for g, pat in (('Weekly', r'\b(weekly|per week|each week)\b'), ('Monthly', r'\b(monthly|per month|each month)\b'),
                       ('Quarterly', r'\b(quarterly|per quarter|each quarter)\b'),
                       ('Yearly', r'\b(yearly|annual(ly)?|per year|each year)\b')):
            if re.search(pat, text):
                base['granularity'] = g
                break
        if when.get('unit') == 'week' and 'granularity' not in base:
            base['granularity'] = 'Weekly'
        if re.search(r'\barea\b', text):
            base['style'] = 'Area'
        elif re.search(r'\b(scatter|dots?|points)\b', text):
            base['style'] = 'Scatter'
        elif re.search(r'\b(bars?|columns?)\b', text):
            base['style'] = 'Bar'
        else:
            base['style'] = 'Line'

        split_dim, split_vals = None, []
        for d in _VALUE_DIMS:
            if len(values.get(d, [])) >= 2:
                split_dim, split_vals = d, values[d]
                break
        if split_dim is None and explicit and dim and len(metrics) == 1 and not values.get(dim):
            col = _col(dim)
            if df is not None and col in df.columns:
                counts = df[col].dropna().value_counts()
                split_dim, split_vals = dim, [str(v) for v in counts.index[:MAX_SERIES]]
                if len(counts) > MAX_SERIES:
                    notes.append(f'Showing the {MAX_SERIES} largest of {len(counts)} groups.')
        if split_dim and len(metrics) == 1:
            return [dict(base, metric=metrics[0], filter_by=split_dim, filter_val=v) for v in split_vals[:MAX_SERIES]]
        filt = next(((d, vs[0]) for d in _VALUE_DIMS if (vs := values.get(d))), None)
        specs = []
        for m in metrics:
            s = dict(base, metric=m)
            if filt:
                s['filter_by'], s['filter_val'] = filt
            specs.append(s)
        return specs

    if wants_time:
        notes.append('That measure can\'t be shown over time, so it is compared by group instead.')
    metrics = [_SNAP_METRIC[k] for k in keys if k in _SNAP_METRIC]
    if not metrics:
        raise ChartRequestError('Hires and departures can only be charted over time. Try '
                                '"hires over the last 12 months".')
    if 'hires' in keys or 'departures' in keys:
        notes.append('Left out hires/departures. They can only be shown over time.')
    group = dim or 'Department'
    if values and not explicit:
        notes.append('By-group charts can\'t be narrowed to one group here. Tick "Dashboard filters" '
                     'in the Analytics tab to chart a filtered set of employees.')
    style = None
    if re.search(r'\b(pie|donut|doughnut)\b', text):
        style = 'Pie'
    elif re.search(r'\bhorizontal\b', text):
        style = 'Horizontal Bar'
    elif re.search(r'\b(vertical|columns?)\b', text):
        style = 'Vertical Bar'
    elif re.search(r'\b(scatter|dots?)\b', text):
        style = 'Scatter'
    return [{'view': 'snapshot', 'metric': m, 'group_by': group, 'style': style} for m in metrics[:3]]


def keyword_suggestion(description: str, df: pd.DataFrame, notes: list[str] | None = None) -> ChartSuggestion:
    text = ' '.join(description.lower().split())
    notes = list(notes or [])
    specs = _keyword_specs(text, df, notes)
    return build_suggestion(specs, df, None, 'keywords', notes)


def build_prompt(description: str, df: pd.DataFrame | None) -> list[dict]:
    depts = sorted(df['Department'].dropna().unique().tolist()) if df is not None and 'Department' in df.columns else []
    roles = sorted(df['Job_Role'].dropna().unique().tolist()) if df is not None and 'Job_Role' in df.columns else []
    system = f"""You turn a plain-English chart request into a chart specification for an HR analytics
dashboard. You only choose settings; a separate engine calculates and draws the chart.

Respond with ONLY a JSON object: {{"title": "<short title>", "series": [ <series>, ... ]}}
Use 1 series normally; use several to compare things (for example hires AND departures, or two departments). Maximum {MAX_SERIES}.

Each series has these fields:
- "view": "time" (a trend across dates) or "snapshot" (comparing groups right now)
- "metric": for time one of {analytics.TIME_SERIES_METRICS}; for snapshot one of {analytics.SNAPSHOT_METRICS}
- "group_by": snapshot only, one of {analytics.GROUP_BY_OPTIONS}
- "filter_by": time only, "None" or one of {analytics.GROUP_BY_OPTIONS}
- "filter_val": time only, "All" or one specific value, e.g. a department name
- "months": time only, whole number of months of history (12 if not stated, 0 for all time)
- "granularity": time only, one of {analytics.GRANULARITIES}
- "style": time: one of {TIME_STYLES}; snapshot: one of {SNAP_STYLES} (Pie only for Total Employees)
- "trend": time only, true to add a trend line

Departments in the data: {depts}
Job roles in the data: {roles}

Examples:
Request: hires vs departures over the last 2 years
{{"title": "Hires vs Departures", "series": [{{"view": "time", "metric": "Hires", "filter_by": "None", "filter_val": "All", "months": 24, "granularity": "Monthly", "style": "Line", "trend": false}}, {{"view": "time", "metric": "Departures", "filter_by": "None", "filter_val": "All", "months": 24, "granularity": "Monthly", "style": "Line", "trend": false}}]}}
Request: average salary by job role as horizontal bars
{{"title": "Average Salary by Job Role", "series": [{{"view": "snapshot", "metric": "Average Salary ($)", "group_by": "Job Role", "style": "Horizontal Bar"}}]}}
Request: turnover rate by department
{{"title": "Turnover by Department", "series": [{{"view": "snapshot", "metric": "Overall Turnover Rate (%)", "group_by": "Department", "style": "Vertical Bar"}}]}}"""
    return [{'role': 'system', 'content': system},
            {'role': 'user', 'content': f'Request: {description}'}]


def parse_llm_output(raw: str) -> tuple[list, str | None]:
    data = json.loads(raw)
    if isinstance(data, list):
        return data, None
    if not isinstance(data, dict):
        raise ValueError('not an object')
    series = data.get('series')
    if series is None and 'metric' in data:
        series = [data]
    if not isinstance(series, list):
        raise ValueError('no series')
    title = data.get('title')
    return series, title.strip()[:80] if isinstance(title, str) and title.strip() else None


def suggest_chart(description: str, df: pd.DataFrame, client=None, model: str = '') -> ChartSuggestion:
    description = (description or '').strip()
    if not description:
        raise ChartRequestError('Describe the chart you want, for example "turnover by department".')
    if df is None or len(df) == 0:
        raise ChartRequestError('Load some employee data first.')

    fallback_note = None
    if client is not None and client.is_available():
        try:
            raw = client.chat(model, build_prompt(description, df), json_mode=True, max_tokens=MAX_TOKENS)
            specs, title = parse_llm_output(raw)
            return build_suggestion(specs, df, title, 'ai')
        except ChartRequestError:
            fallback_note = 'The AI model\'s answer wasn\'t usable, so keyword matching was used instead.'
        except (LocalLLMError, ValueError, TypeError, KeyError):
            fallback_note = 'The AI model couldn\'t be used just now, so keyword matching was used instead.'
    return keyword_suggestion(description, df, [fallback_note] if fallback_note else None)
