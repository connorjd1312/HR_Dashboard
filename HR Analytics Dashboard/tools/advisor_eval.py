# advisor_eval.py
# Capability check for the AI Workforce Advisor's local model.
#
# Runs a fixed set of HR questions (simple → advanced, plus questions it should
# decline) through the real advisor pipeline and checks, for each one:
#   - routing:   did the model pick the right analytics function / metric?
#   - correct:   does the answer contain the right figure (computed independently
#                with core/analytics.py)?
#   - faithful:  does every number in the answer appear in the data it was given
#                (i.e. no invented or self-calculated numbers)?
#   - time:      seconds to answer on this machine.
#
# Needs the downloaded model (models/*.gguf) — it is NOT part of the pytest suite.
# Usage (from the 'HR Analytics Dashboard' folder):
#   python tools/advisor_eval.py [--out report.md] [--limit N]

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from core import analytics, context_builder, data_cleaner, data_loader, query_router  # noqa: E402
from core.local_llm_client import LocalLLMClient  # noqa: E402

DATA_FILE = ROOT / 'Default documents' / 'all_departments.csv'

T = 'Overall Turnover Rate (%)'
A = 'Attrition (Voluntary Leavers) Rate (%)'


def _top(series: pd.Series) -> str:
    return str(series.astype(float).idxmax())


def _bottom(series: pd.Series) -> str:
    return str(series.astype(float).idxmin())


# Each case: question, acceptable routes {function: required params subset},
# and a function computing the text the answer must contain (None = no check).
CASES = [
    # ── Simple: one headline figure
    dict(level='Simple', q="What's our overall turnover rate?",
         routes={'overall_kpi': {'metric': T}},
         expect=lambda df: analytics.kpi_value(df, T)),
    dict(level='Simple', q='How many active employees do we have?',
         routes={'overall_kpi': {'metric': 'Active Employees'}},
         expect=lambda df: analytics.kpi_value(df, 'Active Employees')),
    dict(level='Simple', q='What is the average salary?',
         routes={'overall_kpi': {'metric': 'Avg Salary ($)'}},
         expect=lambda df: analytics.kpi_value(df, 'Avg Salary ($)')),
    dict(level='Simple', q='What is our attrition rate?',
         routes={'overall_kpi': {'metric': A}},
         expect=lambda df: analytics.kpi_value(df, A)),

    # ── Breakdowns / comparisons
    dict(level='Breakdown', q='Which department has the highest attrition?',
         routes={'breakdown_kpi': {'metric': A, 'group_by': 'Department'},
                 'department_comparison': {'metric': A}},
         expect=lambda df: _top(analytics.kpi_breakdown(df, A, 'Department'))),
    dict(level='Breakdown', q='Which department has the lowest average salary?',
         routes={'breakdown_kpi': {'metric': 'Avg Salary ($)', 'group_by': 'Department'},
                 'department_comparison': {'metric': 'Average Salary ($)'}},
         expect=lambda df: _bottom(analytics.kpi_breakdown(df, 'Avg Salary ($)', 'Department'))),
    dict(level='Breakdown', q='Show me overall turnover by age group',
         routes={'breakdown_kpi': {'metric': T, 'group_by': 'Age Group'}},
         expect=lambda df: _top(analytics.kpi_breakdown(df, T, 'Age Group'))),
    dict(level='Breakdown', q='Compare average tenure between Sales and Engineering',
         routes={'department_comparison': {'metric': 'Average Tenure (yrs)'},
                 'breakdown_kpi': {'metric': 'Avg Tenure (yrs)', 'group_by': 'Department'}},
         expect=lambda df: _top(analytics.dept_comparison(df, ['Sales', 'Engineering'], 'Average Tenure (yrs)'))),

    # ── Trends over time
    dict(level='Trend', q='How have departures changed over the last 6 months?',
         routes={'time_series_trend': {'metric': 'Departures per Month'}},
         expect=None),
    dict(level='Trend', q='Show the hiring trend for the past year',
         routes={'time_series_trend': {'metric': 'Hires per Month'}},
         expect=None),

    # ── Forecasts
    dict(level='Forecast', q='Forecast hires for the next quarter',
         routes={'forecast': {'metric': 'Hires per Month'}},
         expect=None),
    dict(level='Forecast', q='Will departures go up or down over the next 6 months?',
         routes={'forecast': {'metric': 'Departures per Month'}},
         expect=None),

    # ── Advanced: need more than one figure or a calculation on top of the data
    dict(level='Advanced', q='What is the difference between our overall turnover rate and our attrition rate?',
         routes={'general_summary': {}, 'unsupported': {}, 'overall_kpi': {}},
         expect=None),
    dict(level='Advanced', q='What is the average salary of the department with the highest turnover?',
         routes={'breakdown_kpi': {}, 'department_comparison': {}, 'unsupported': {}},
         expect=None),
    dict(level='Advanced', q='What percentage of all leavers were terminated rather than resigning?',
         routes={'breakdown_kpi': {'group_by': 'Status'}, 'unsupported': {}},
         expect=None),

    # ── Should be declined (not in the data / what-if / causes)
    dict(level='Decline', q='What would happen to turnover if we gave everyone a 10% pay rise?',
         routes={'unsupported': {}}, expect=None),
    dict(level='Decline', q='Why are people leaving Customer Support?',
         routes={'unsupported': {}}, expect=None),
    dict(level='Decline', q="What is John Smith's salary?",
         routes={'unsupported': {}}, expect=None),
]

_NUM = re.compile(r'(?<![\w.])-?\d[\d,]*(?:\.\d+)?')


def _numbers(text: str) -> set[float]:
    out = set()
    for m in _NUM.findall(text):
        try:
            out.add(round(float(m.replace(',', '')), 1))
        except ValueError:
            pass
    return out


def _allowed_numbers(question: str, context: dict | None, answer_extra: str) -> set[float]:
    # Every number the answer may legitimately contain: anything in the question,
    # the context sent to the model (values, key facts, params, dates) and the
    # fixed text of direct answers.
    allowed = _numbers(question) | _numbers(answer_extra)
    if context:
        blob = json.dumps(context, ensure_ascii=False)
        allowed |= _numbers(blob)
        for d in re.findall(r'(\d{4})-(\d{2})-(\d{2})', blob):   # 2026-08-31 → 2026, 8, 31
            allowed |= {float(x) for x in d}
    allowed |= {float(date.today().year)}
    return allowed


def _route_ok(case, route) -> bool:
    need = case['routes'].get(route.function)
    if need is None:
        return False
    return all(route.params.get(k) == v for k, v in need.items())


def run(limit: int | None):
    loaded = data_loader.load_file(str(DATA_FILE))
    df = loaded[0] if isinstance(loaded, tuple) else loaded
    df = data_cleaner.clean(df)
    df = df[0] if isinstance(df, tuple) else df

    client = LocalLLMClient()
    models = client.list_models()
    if not models:
        sys.exit('Local model not downloaded — open the AI Advisor tab and download it first.')
    model = models[0]

    t0 = time.time()
    client.chat(model, [{'role': 'user', 'content': 'Hi'}])   # load the model once
    load_secs = time.time() - t0

    rows = []
    for case in CASES[:limit]:
        q = case['q']
        t = time.time()
        route = query_router.route_query(client, model, q, df)
        result = query_router.execute(route, df)
        answer = query_router.direct_answer(route, result)
        context = None
        used_llm = answer is None
        if used_llm:
            context = context_builder.build_context(q, route.function, route.params, result)
            answer = query_router.explain_result(client, model, q, context)
        secs = time.time() - t

        expected = case['expect'](df) if case['expect'] else None
        correct = None if expected is None else (str(expected).lower() in answer.lower())
        extra = '' if used_llm else answer
        invented = sorted(_numbers(answer) - _allowed_numbers(q, context, extra))
        rows.append(dict(level=case['level'], q=q, function=route.function,
                         params=route.params, route_ok=_route_ok(case, route),
                         expected=expected, correct=correct, invented=invented,
                         used_llm=used_llm, secs=secs, answer=answer.strip()))
        print(f"[{case['level']}] {q}\n   -> {route.function} {route.params} | "
              f"route {'OK' if rows[-1]['route_ok'] else 'WRONG'} | "
              f"correct {correct} | invented {invented} | {secs:.0f}s\n   {answer.strip()[:300]}\n",
              flush=True)
    return rows, load_secs, len(df)


def _yn(v) -> str:
    return '—' if v is None else ('✅' if v else '❌')


def report(rows, load_secs, n_rows) -> str:
    lines = [
        '# AI Advisor — local model capability check',
        '',
        f'Run on {date.today():%d %b %Y} with the bundled local model against '
        f'`Default documents/all_departments.csv` ({n_rows:,} employees). '
        f'Model load time: {load_secs:.0f}s.',
        '',
        '| Level | Questions | Routed correctly | Correct figure | No invented numbers | Avg time |',
        '|---|---|---|---|---|---|',
    ]
    for level in dict.fromkeys(r['level'] for r in rows):
        rs = [r for r in rows if r['level'] == level]
        checked = [r for r in rs if r['correct'] is not None]
        lines.append(
            f"| {level} | {len(rs)} | {sum(r['route_ok'] for r in rs)}/{len(rs)} | "
            + (f"{sum(r['correct'] for r in checked)}/{len(checked)}" if checked else '—')
            + f" | {sum(not r['invented'] for r in rs)}/{len(rs)} | "
            f"{sum(r['secs'] for r in rs) / len(rs):.0f}s |"
        )
    lines += ['', '## Every question', '']
    for r in rows:
        lines += [
            f"**[{r['level']}] {r['q']}**  ",
            f"Route: `{r['function']}` {json.dumps(r['params'])} — {_yn(r['route_ok'])} · "
            f"Correct figure: {_yn(r['correct'])}"
            + (f" (expected {r['expected']})" if r['expected'] is not None else '')
            + f" · Invented numbers: {', '.join(map(str, r['invented'])) or 'none'} · "
            f"{'model-written' if r['used_llm'] else 'exact (no model)'} · {r['secs']:.0f}s",
            '',
            f"> {r['answer']}".replace('\n', '\n> '),
            '',
        ]
    return '\n'.join(lines)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=None, help='write a markdown report here')
    ap.add_argument('--limit', type=int, default=None, help='only run the first N questions')
    args = ap.parse_args()
    rows, load_secs, n = run(args.limit)
    text = report(rows, load_secs, n)
    if args.out:
        Path(args.out).write_text(text, encoding='utf-8')
        print(f'Report written to {args.out}')
    else:
        print(text)
