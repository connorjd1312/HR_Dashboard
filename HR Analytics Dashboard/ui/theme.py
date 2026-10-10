# theme.py
# One place for the app's colours, fonts and shared widget styles so every tab
# looks the same. Individual widgets import the constants they need; the
# app-wide stylesheet and chart style are applied once by apply_app_theme().

from PyQt6.QtGui import QFont
import matplotlib as mpl

# ── Palette ──────────────────────────────────────────────────────────────────
NAVY        = '#1F3864'   # headers, primary buttons, KPI cards
BLUE        = '#2E75B6'   # accents, hover, chart bars
NAVY_PRESS  = '#163060'
BG          = '#F5F7FA'   # panel backgrounds
BORDER      = '#E0E0E0'
INPUT_BORDER = '#CCCCCC'
TEXT        = '#333333'
TEXT_MUTED  = '#666666'
GREEN       = '#1E8449'
RED         = '#C0392B'
RED_BG      = '#FADBD8'
HIGHLIGHT   = '#F5A623'   # hover outline on clickable chart parts

# Categorical colours for pies / multi-series charts
CHART_COLORS = [
    '#1F3864', '#2E75B6', '#1E8449', '#C0392B',
    '#D4AC0D', '#5B2C6F', '#117A65', '#E67E22',
    '#7F8C8D', '#34495E',
]

# ── Typography ───────────────────────────────────────────────────────────────
FONT_FAMILY = 'Segoe UI'
FONT_SMALL  = 11   # px — hints, captions, field labels
FONT_BODY   = 12   # px — buttons, inputs, table text
FONT_TITLE  = 14   # px — section / panel titles

# ── Shared widget styles ─────────────────────────────────────────────────────
BTN_PRIMARY = f'''
    QPushButton {{
        background-color: {NAVY}; color: white;
        border-radius: 5px; padding: 6px 14px;
        font-size: {FONT_BODY}px; border: none;
    }}
    QPushButton:hover    {{ background-color: {BLUE}; }}
    QPushButton:pressed  {{ background-color: {NAVY_PRESS}; }}
    QPushButton:disabled {{ background-color: #9AA5B1; }}
'''

BTN_SECONDARY = f'''
    QPushButton {{
        background-color: white; color: {TEXT};
        border-radius: 5px; padding: 6px 14px;
        font-size: {FONT_BODY}px; border: 1px solid {INPUT_BORDER};
    }}
    QPushButton:hover    {{ background-color: #F0F4FF; border-color: {BLUE}; }}
    QPushButton:disabled {{ color: #AAAAAA; }}
'''

BTN_DANGER_OUTLINE = f'''
    QPushButton {{
        background-color: white; color: {RED};
        border: 1px solid {RED}; border-radius: 5px;
        padding: 6px 14px; font-size: {FONT_BODY}px;
    }}
    QPushButton:hover    {{ background-color: #FDECEA; }}
    QPushButton:pressed  {{ background-color: {RED_BG}; }}
    QPushButton:disabled {{ color: #C9A6A1; border-color: #E6C6C2; }}
'''

# Small round ✕ button used on cards and chart panels
BTN_ICON_CLOSE = f'''
    QPushButton {{
        color: #555555; background: #F0F0F0; border: 1px solid {INPUT_BORDER};
        border-radius: 11px; font-size: {FONT_SMALL}px; font-weight: bold;
    }}
    QPushButton:hover {{ background: #E74C3C; color: white; border-color: {RED}; }}
'''

BTN_LINK = f'''
    QPushButton {{
        border: none; color: {TEXT_MUTED}; background: transparent;
        padding: 6px 12px; font-size: {FONT_BODY}px;
    }}
    QPushButton:hover {{ color: {TEXT}; text-decoration: underline; }}
'''

LABEL_TAG     = f'font-size: {FONT_SMALL}px; color: {TEXT_MUTED}; background: transparent;'
LABEL_FIELD   = f'font-size: {FONT_SMALL}px; font-weight: bold; color: #444444; background: transparent;'
LABEL_HINT    = f'font-size: {FONT_SMALL}px; color: #777777; background: transparent;'
LABEL_SECTION = f'font-size: {FONT_TITLE}px; font-weight: bold; color: {NAVY}; background: transparent;'

# Inputs (combo / date / text boxes) share one look; set app-wide below so
# widgets don't need their own stylesheet.
_INPUT_QSS = f'''
    QComboBox, QDateEdit, QLineEdit {{
        border: 1px solid {INPUT_BORDER}; border-radius: 4px;
        padding: 4px 8px; background: white;
        font-size: {FONT_BODY}px; color: {TEXT};
    }}
    QComboBox:hover, QDateEdit:hover {{ border-color: {BLUE}; }}
    QComboBox:focus, QDateEdit:focus, QLineEdit:focus {{ border-color: {BLUE}; }}
    QComboBox QAbstractItemView {{
        border: 1px solid {INPUT_BORDER}; background: white;
        selection-background-color: {BLUE}; selection-color: white;
    }}
'''

COMBO_STYLE = _INPUT_QSS

# Navy tooltips. A container that sets its own background must append this,
# or its children's tooltips pick up that background behind the white text.
TOOLTIP_QSS = f'''
    QToolTip {{
        background-color: {NAVY}; color: white; border: none;
        padding: 5px 8px; font-size: {FONT_SMALL}px;
    }}
'''

_APP_QSS = _INPUT_QSS + TOOLTIP_QSS + f'''

    /* Main tabs (Dashboard / Analytics / Forecasting) and sub-tabs */
    QTabWidget::pane {{ border: 1px solid {BORDER}; top: -1px; background: white; }}
    QTabBar::tab {{
        background: {BG}; color: {TEXT_MUTED};
        border: 1px solid {BORDER}; border-bottom: none;
        padding: 7px 18px; margin-right: 2px;
        font-size: {FONT_BODY}px;
        border-top-left-radius: 5px; border-top-right-radius: 5px;
    }}
    QTabBar::tab:hover    {{ color: {NAVY}; background: #EAF1FA; }}
    QTabBar::tab:selected {{
        background: white; color: {NAVY}; font-weight: bold;
        border-top: 3px solid {BLUE};
    }}

    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: #C5CCD6; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {BLUE}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

    QTableWidget {{ font-size: {FONT_BODY}px; gridline-color: #E8E8E8; }}

'''


# Date picker pop-up calendar: navy header so the month and year are readable.
# Applied to each calendar directly (see style_date_edit) because the pop-up
# doesn't pick up the app-wide stylesheet for its navigation bar.
CALENDAR_STYLE = f'''
    QCalendarWidget QWidget#qt_calendar_navigationbar {{ background-color: {NAVY}; }}
    QCalendarWidget QToolButton {{
        color: white; background: transparent; border: none;
        font-size: {FONT_BODY}px; font-weight: bold; padding: 4px 8px;
    }}
    QCalendarWidget QToolButton:hover {{ background-color: {BLUE}; border-radius: 4px; }}
    QCalendarWidget QToolButton::menu-indicator {{ image: none; }}
    QCalendarWidget QMenu {{ background: white; color: {TEXT}; }}
    QCalendarWidget QSpinBox {{
        background: white; color: {TEXT}; border: 1px solid {INPUT_BORDER};
        selection-background-color: {BLUE}; selection-color: white;
    }}
    QCalendarWidget QAbstractItemView:enabled {{
        color: {TEXT}; background: white;
        selection-background-color: {BLUE}; selection-color: white;
    }}
'''


def style_date_edit(date_edit):
    # Shared look for a QDateEdit and its pop-up calendar.
    date_edit.setStyleSheet(COMBO_STYLE)
    date_edit.calendarWidget().setStyleSheet(CALENDAR_STYLE)


def apply_chart_style():
    # Consistent Matplotlib look for every chart in the app.
    mpl.rcParams.update({
        'font.family':       'sans-serif',
        'font.sans-serif':   [FONT_FAMILY, 'Arial', 'DejaVu Sans'],
        'font.size':         9,
        'axes.titlesize':    11,
        'axes.titleweight':  'bold',
        'axes.titlecolor':   TEXT,
        'axes.labelsize':    9,
        'axes.labelcolor':   '#444444',
        'axes.edgecolor':    '#999999',
        'axes.spines.top':   False,
        'axes.spines.right': False,
        'axes.prop_cycle':   mpl.cycler(color=CHART_COLORS),
        'xtick.labelsize':   9,
        'ytick.labelsize':   9,
        'xtick.color':       '#444444',
        'ytick.color':       '#444444',
        'grid.color':        '#DDDDDD',
        'grid.linestyle':    '--',
        'legend.fontsize':   9,
        'legend.frameon':    False,
    })


def apply_app_theme(app):
    # App-wide font, stylesheet and chart style. Safe to call more than once.
    app.setFont(QFont(FONT_FAMILY, 9))
    app.setStyleSheet(_APP_QSS)
    apply_chart_style()
