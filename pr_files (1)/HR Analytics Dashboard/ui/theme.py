# theme.py
# One place for the app's colours, fonts and shared widget styles so every tab
# looks the same. Individual widgets import the constants they need; the
# app-wide stylesheet and chart style are applied once by apply_app_theme().

import re

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QWidget
import matplotlib as mpl
import matplotlib.colors

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


MODES = ('light', 'dark', 'system')

DARK = {
    'window': '#12161F',
    'bg': '#171D29',
    'surface': '#1F2633',
    'surface_alt': '#262F3F',
    'text': '#E6EAF2',
    'text_soft': '#C3CAD8',
    'text_muted': '#9AA4B8',
    'border': '#35405A',
}

_DARK_BACKGROUNDS = {
    'white': DARK['surface'], '#f5f7fa': DARK['bg'],
    '#f0f4ff': '#222C40', '#f7faff': '#222C40', '#f8faff': '#222C40',
    '#eaf1fa': '#243049', '#ebf5fb': '#243049', '#e8eef7': '#243049', '#e1eafb': '#2A3956',
    '#d6eaf8': '#2A3956', '#eaecf0': '#2A3242', '#f0f0f0': '#2A3242', '#f8f9fb': '#232B3A',
    '#e5e7eb': DARK['border'], '#c5ccd6': '#46506A',
    '#fdecea': '#3A2326', '#fadbd8': '#4A2A2D',
    '#e9f7ef': '#14301F', '#fff4e5': '#3A2D14',
    '#f7fafd': '#222C40', '#f0f5fa': '#222C40', '#eceff3': '#2A3242',
}
_DARK_TEXT = {
    '#333333': DARK['text'],
    '#444444': DARK['text_soft'], '#555555': DARK['text_soft'],
    '#666666': DARK['text_muted'], '#777777': DARK['text_muted'], '#888888': DARK['text_muted'],
    '#999999': DARK['text_muted'], '#aaaaaa': '#7C869A', '#c9a6a1': '#7A5A56',
    '#bbbbbb': '#6B7489',
    '#1f3864': '#8DB4F2',
    '#2e75b6': '#6CA9E6',
    '#1e6b3a': '#7DDC9C', '#7a4b00': '#F5C77E', '#b9770e': '#F0B35A',
    '#c0392b': '#FF8F82', '#1e8449': '#58C98A',
}
_DARK_BORDERS = {
    '#e0e0e0': DARK['border'], '#e5e7eb': DARK['border'], '#e8e8e8': DARK['border'],
    '#dddddd': DARK['border'], '#cccccc': '#44506B', '#c9d7f0': '#3B4C70', '#b9cce8': '#3B4C70',
    '#b0b7c1': '#4A5470', '#d8dce3': DARK['border'], '#999999': '#4A5470',
    '#a9dfbf': '#2E6B45', '#f5c77e': '#7A5A1E', '#e6b0aa': '#7A3A36',
    '#e6c6c2': '#5A3A38', 'white': DARK['surface'], '#eeeeee': '#2E384E',
    '#dce1e8': '#3A4560', '#b7d3ea': '#3B4C70',
}

_COLOR_TOKEN = re.compile(r'#[0-9a-fA-F]{3}(?![0-9a-fA-F])|#[0-9a-fA-F]{6}(?![0-9a-fA-F])|\bwhite\b', re.I)
_BODY = re.compile(r'\{([^{}]*)\}')

_resolved_mode = 'light'
_setting = 'light'


def is_dark() -> bool:
    return _resolved_mode == 'dark'


def _norm(token: str) -> str:
    t = token.lower()
    if len(t) == 4 and t[0] == '#':
        t = '#' + ''.join(c * 2 for c in t[1:])
    return t


def _map_value(value: str, table: dict) -> str:
    return _COLOR_TOKEN.sub(lambda m: table.get(_norm(m.group(0)), m.group(0)), value)


def _adapt_declarations(body: str) -> str:
    out = []
    for decl in body.split(';'):
        prop, sep, value = decl.partition(':')
        name = prop.strip().lower()
        if not sep:
            out.append(decl)
        elif name in ('background', 'background-color', 'alternate-background-color'):
            out.append(f'{prop}:{_map_value(value, _DARK_BACKGROUNDS)}')
        elif name == 'color':
            out.append(f'{prop}:{_map_value(value, _DARK_TEXT)}')
        elif name.startswith('border') or name in ('gridline-color', 'outline-color'):
            out.append(f'{prop}:{_map_value(value, _DARK_BORDERS)}')
        else:
            out.append(decl)
    return ';'.join(out)


def adapt_qss(qss: str) -> str:
    if not qss or not is_dark():
        return qss
    if '{' in qss:
        return _BODY.sub(lambda m: '{' + _adapt_declarations(m.group(1)) + '}', qss)
    return _adapt_declarations(qss)


def text_muted() -> str:
    return DARK['text_muted'] if is_dark() else '#555555'


def heading_colour() -> str:
    return _DARK_TEXT['#1f3864'] if is_dark() else NAVY


def border_colour() -> str:
    return DARK['border'] if is_dark() else '#E0E0E0'


_SRC, _APPLIED = '_hr_light_qss', '_hr_applied_qss'


def _adapt_widget(w) -> None:
    cur = w.styleSheet()
    if not cur or cur == w.property(_APPLIED):
        return
    adapted = adapt_qss(cur)
    w.setProperty(_SRC, cur)
    w.setProperty(_APPLIED, adapted)
    if adapted != cur:
        w.setStyleSheet(adapted)


class _StyleAdapter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.StyleChange and isinstance(obj, QWidget):
            _adapt_widget(obj)
        return False


_adapter: _StyleAdapter | None = None


def _restyle_widgets(app) -> None:
    for w in app.allWidgets():
        cur = w.styleSheet()
        if not cur:
            continue
        src = w.property(_SRC)
        if src is None or cur != w.property(_APPLIED):
            src = cur
        adapted = adapt_qss(src)
        w.setProperty(_SRC, src)
        w.setProperty(_APPLIED, adapted)
        if adapted != cur:
            w.setStyleSheet(adapted)


def _dark_palette() -> QPalette:
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: DARK['window'], QPalette.ColorRole.WindowText: DARK['text'],
        QPalette.ColorRole.Base: DARK['surface'], QPalette.ColorRole.AlternateBase: DARK['surface_alt'],
        QPalette.ColorRole.Text: DARK['text'], QPalette.ColorRole.Button: '#2A3242',
        QPalette.ColorRole.ButtonText: DARK['text'], QPalette.ColorRole.BrightText: '#FFFFFF',
        QPalette.ColorRole.ToolTipBase: NAVY, QPalette.ColorRole.ToolTipText: '#FFFFFF',
        QPalette.ColorRole.PlaceholderText: '#7C869A', QPalette.ColorRole.Highlight: BLUE,
        QPalette.ColorRole.HighlightedText: '#FFFFFF', QPalette.ColorRole.Link: '#6CA9E6',
        QPalette.ColorRole.LinkVisited: '#B58BD6', QPalette.ColorRole.Light: '#3A4560',
        QPalette.ColorRole.Midlight: '#2E384E', QPalette.ColorRole.Mid: '#242C3C',
        QPalette.ColorRole.Dark: '#0E1119', QPalette.ColorRole.Shadow: '#000000',
    }
    for role, colour in roles.items():
        p.setColor(role, QColor(colour))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor('#6B7489'))
    return p


def system_prefers_dark(app) -> bool:
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        return False


def resolve(mode: str, app) -> str:
    if mode == 'system':
        return 'dark' if system_prefers_dark(app) else 'light'
    return 'dark' if mode == 'dark' else 'light'


def current_setting() -> str:
    return _setting


def set_mode(app, mode: str) -> bool:
    global _resolved_mode, _setting, _adapter
    if mode not in MODES:
        mode = 'light'
    _setting = mode
    new = resolve(mode, app)
    changed = new != _resolved_mode
    _resolved_mode = new
    if _adapter is None:
        _adapter = _StyleAdapter(app)
        app.installEventFilter(_adapter)
    app.setPalette(_dark_palette() if is_dark() else app.style().standardPalette())
    app.setStyleSheet(adapt_qss(_APP_QSS))
    apply_chart_style()
    _restyle_widgets(app)
    return changed


CHART_COLORS_DARK = ['#5B8FD6', '#4BA3E0', '#3FBF7F', '#E0645A', '#E3C04A',
                     '#A878C9', '#3CB8A0', '#F09A4A', '#9AA5B1', '#7F93B2']
_DARK_SERIES = {'#1f3864': '#9CC0FF', '#5b2c6f': '#B58BD6', '#34495e': '#8FA3BA'}


def _chart_dark() -> bool:
    # Follows the active rcParams, so code under an rc_context (the PDF report) stays light.
    try:
        r, g, b = mpl.colors.to_rgb(mpl.rcParams['axes.facecolor'])
    except ValueError:
        return False
    return 0.299 * r + 0.587 * g + 0.114 * b < 0.5


def chart_palette() -> list:
    return CHART_COLORS_DARK if _chart_dark() else CHART_COLORS


def chart_color(colour: str) -> str:
    return _DARK_SERIES.get(str(colour).lower(), colour) if _chart_dark() else colour


def chart_surface() -> str:
    return mpl.rcParams['axes.facecolor']


def chart_text() -> str:
    return mpl.rcParams['text.color']


def chart_muted() -> str:
    return mpl.rcParams['axes.labelcolor']


def apply_chart_style():
    dark = is_dark()
    text, label, edge, grid = ((DARK['text'], DARK['text_soft'], '#5A6580', DARK['border']) if dark
                               else (TEXT, '#444444', '#999999', '#DDDDDD'))
    mpl.rcParams.update({
        'font.family':       'sans-serif',
        'font.sans-serif':   [FONT_FAMILY, 'Arial', 'DejaVu Sans'],
        'font.size':         9,
        'figure.facecolor':  DARK['surface'] if dark else 'white',
        'axes.facecolor':    DARK['surface'] if dark else 'white',
        'savefig.facecolor': 'auto',
        'text.color':        text,
        'axes.titlesize':    11,
        'axes.titleweight':  'bold',
        'axes.titlecolor':   text,
        'axes.labelsize':    9,
        'axes.labelcolor':   label,
        'axes.edgecolor':    edge,
        'axes.spines.top':   False,
        'axes.spines.right': False,
        'axes.prop_cycle':   mpl.cycler(color=CHART_COLORS_DARK if dark else CHART_COLORS),
        'xtick.labelsize':   9,
        'ytick.labelsize':   9,
        'xtick.color':       label,
        'ytick.color':       label,
        'grid.color':        grid,
        'grid.linestyle':    '--',
        'legend.fontsize':   9,
        'legend.frameon':    False,
    })


def apply_app_theme(app, mode: str | None = None):
    app.setFont(QFont(FONT_FAMILY, 9))
    set_mode(app, mode if mode is not None else _setting)
