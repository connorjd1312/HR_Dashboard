# Quick Guide dialog

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextBrowser, QPushButton

from core import analytics
from ui import theme

_GUIDE = '''
<h2 style="color:{navy}">Quick Guide</h2>

<h3 style="color:{navy}">Dashboard</h3>
<ul>
  <li><b>Filters</b> (left), choose a department, job role, status, hire-date range and so on,
      then click <b>Apply Filters</b>. The blue bar at the top shows the time period you're looking at.</li>
  <li><b>KPI cards</b>: headline numbers. Hover a card to see what it means; click it to see a
      breakdown by department, job role, status and more. The small ▲/▼ line on each card
      compares it with the <b>previous period</b>: the same length of time just before your chosen dates
      (e.g. 1 Jan 2025 – 9 Oct 2026 is compared with 26 Mar 2023 – 31 Dec 2024). Green is good news,
      red is bad news, grey is neutral. Use <b>+ Add Card</b> to add others, ✕ to remove.</li>
  <li><b>Drill down</b>: click any bar or slice (it highlights when you hover) to focus on that group.
      Keep clicking to go deeper; <b>Back</b> goes up one level.</li>
  <li><b>Compare Charts</b>: show up to 4 charts side by side. Drag the grey bars between charts
      to resize them, or click <b>Enlarge</b> to fill the screen with one chart.</li>
  <li>Drag a KPI card left or right to reorder the cards. With several charts showing, drag the handle
      at the top left of a chart onto another chart to swap them. Your layout is remembered next time,
      and the Reset button restores the original.</li>
  <li>Double-click any row in an employee table to open that person's profile.</li>
</ul>

<h3 style="color:{navy}">Employees</h3>
<ul>
  <li>Search by name, department, job role or status (Ctrl+F jumps here). Every word you type must match,
      so "sales manager" finds Sales Managers. Narrow further with the department and status lists.</li>
  <li>Click a person to see their details and how their salary, tenure, absence and leave compare with
      their department.</li>
</ul>

<h3 style="color:{navy}">Analytics</h3>
<ul>
  <li>Build your own charts: click <b>+ Add Series</b>, then choose
      <b>Over Time</b> (a trend across dates) or <b>Snapshot</b> (compare groups today).</li>
  <li>Add several series to compare them on one chart. Use <b>+ New Chart</b> to keep more than one chart.</li>
  <li>Describe a chart lets you type what you want in plain words (for example, hires vs departures over
      the last 2 years) and preview it before adding it. It uses the local AI model if you have downloaded
      it, and keyword matching if not.</li>
  <li>Undo and Redo (or Ctrl+Z and Ctrl+Y) reverse and repeat changes to your charts.</li>
  <li><b>Focus</b> hides the side panels for a bigger chart. <b>Save</b> / <b>Load</b> keep chart setups for later,
      and <b>PNG</b> / <b>PDF</b> / <b>Copy</b> export the chart.</li>
</ul>

<h3 style="color:{navy}">Forecasting</h3>
<ul>
  <li>Projects a metric forward from the last 2 years of data. Pick the metric, department,
      method, how much history to show (all of it by default) and how far ahead to look.</li>
  <li><b>Smoothed Trend</b> suits numbers whose direction shifts; <b>Linear Trend</b> suits steadily rising or
      falling numbers; <b>Moving Average</b> suits numbers that go up and down.</li>
  <li>The shaded band is the likely range: where the real number should land 8 times out of 10,
      based on how far past forecasts were off. Forecasts are estimates, not guarantees.</li>
</ul>

<h3 style="color:{navy}">AI Advisor</h3>
<ul>
  <li>Ask questions about your workforce data in plain English, e.g. "What's our turnover by department?".
      Click a suggestion to get started.</li>
  <li>The advisor runs entirely on this computer, no data leaves the machine. The first time,
      it needs a one-time model download.</li>
</ul>

<h3 style="color:{navy}">Reports, themes and settings</h3>
<ul>
  <li>Export PDF Summary Report (File menu, Ctrl+P) creates a printable summary with key figures,
      highlights and charts. You choose what to include.</li>
  <li>The Theme item in the View menu switches between light, dark or following your computer. The Dark
      or Light button at the top right does it in one click (Ctrl+Shift+D).</li>
  <li>The app remembers your window, theme, dashboard layout and the files you last used, and reopens
      those files next time. You can turn that off in the File menu. Open Recent lists earlier files.</li>
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
        if text in seen:  # skip entries that share the same wording
            continue
        seen.add(text)
        rows.append(f'<tr><td style="border-bottom:1px solid {theme.border_colour()}"><b>{name}</b></td>'
                    f'<td style="border-bottom:1px solid {theme.border_colour()}">{text}</td></tr>')
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
        browser.setHtml(_GUIDE.format(navy=theme.heading_colour(), metrics=_metric_rows()))
        v.addWidget(browser)

        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton('Close')
        close.setStyleSheet(theme.BTN_PRIMARY)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        v.addLayout(row)
