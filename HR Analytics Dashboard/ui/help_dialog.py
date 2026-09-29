# help_dialog.py
# Quick Guide shown from Help > Quick Guide (F1): how to use each tab and what
# every metric means, so new users can find their way around without training.

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextBrowser, QPushButton

from core import analytics
from ui import theme

_GUIDE = '''
<h2 style="color:{navy}">Quick Guide</h2>

<h3 style="color:{navy}">Dashboard</h3>
<ul>
  <li><b>Filters</b> (left) — choose a department, job role, status, hire-date range and so on,
      then click <b>Apply Filters</b>. The blue bar at the top shows the time period you're looking at.</li>
  <li><b>KPI cards</b> — headline numbers. Hover a card to see what it means; click it to see a
      breakdown by department, job role, status and more. Use <b>+ Add Card</b> to add others, ✕ to remove.</li>
  <li><b>Drill down</b> — click any bar or slice (it highlights when you hover) to focus on that group.
      Keep clicking to go deeper; <b>Back</b> goes up one level.</li>
  <li><b>Compare Charts</b> — show up to 4 charts side by side. Drag the grey bars between charts
      to resize them, or click <b>Enlarge</b> to fill the screen with one chart.</li>
</ul>

<h3 style="color:{navy}">Analytics</h3>
<ul>
  <li>Build your own charts: click <b>+ Add Series</b>, then choose
      <b>Over Time</b> (a trend across dates) or <b>Snapshot</b> (compare groups today).</li>
  <li>Add several series to compare them on one chart. Use <b>+ New Chart</b> to keep more than one chart.</li>
  <li><b>Focus</b> hides the side panels for a bigger chart. <b>Save</b> / <b>Load</b> keep chart setups for later,
      and <b>PNG</b> / <b>PDF</b> / <b>Copy</b> export the chart.</li>
</ul>

<h3 style="color:{navy}">Forecasting</h3>
<ul>
  <li>Projects a metric forward from the last 2 years of data. Pick the metric, department,
      method and how far ahead to look.</li>
  <li><b>Linear Trend</b> suits steadily rising or falling numbers; <b>Moving Average</b> suits
      numbers that go up and down. Forecasts are estimates, not guarantees.</li>
</ul>

<h3 style="color:{navy}">AI Advisor</h3>
<ul>
  <li>Ask questions about your workforce data in plain English, e.g. "What's our turnover by department?".
      Click a suggestion to get started.</li>
  <li>The advisor runs entirely on this computer — no data leaves the machine. The first time,
      it needs a one-time model download.</li>
</ul>

<h3 style="color:{navy}">What the metrics mean</h3>
<table cellspacing="0" cellpadding="5" style="border-collapse:collapse">
{metrics}
</table>
'''


def _metric_rows() -> str:
    rows = []
    seen = set()
    for name, text in analytics.METRIC_DESCRIPTIONS.items():
        if text in seen:   # skip duplicate wording (e.g. 'Avg Salary' vs 'Average Salary')
            continue
        seen.add(text)
        rows.append(f'<tr><td style="border-bottom:1px solid #E0E0E0"><b>{name}</b></td>'
                    f'<td style="border-bottom:1px solid #E0E0E0">{text}</td></tr>')
    return '\n'.join(rows)


class HelpDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Quick Guide')
        self.resize(720, 640)

        v = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setStyleSheet(f'QTextBrowser {{ border: none; font-size: {theme.FONT_BODY}px; }}')
        browser.setHtml(_GUIDE.format(navy=theme.NAVY, metrics=_metric_rows()))
        v.addWidget(browser)

        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton('Close')
        close.setStyleSheet(theme.BTN_PRIMARY)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        v.addLayout(row)
