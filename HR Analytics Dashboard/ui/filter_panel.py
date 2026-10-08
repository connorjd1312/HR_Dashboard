from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QDateEdit, QPushButton, QFrame, QScrollArea,
)
from PyQt6.QtCore import pyqtSignal, QDate, Qt

from core import analytics

from ui import theme


# Default start of the Hire Date filter when data is first loaded or reset
DEFAULT_HIRE_FROM = QDate(2025, 1, 1)


class FilterPanel(QWidget):
    filters_changed = pyqtSignal(dict)

    def __init__(self, df, parent=None):
        super().__init__(parent)
        self._df = df
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet('background-color: white;')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet('background-color: #1F3864;')
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 0, 14, 0)
        title = QLabel('Filters')
        title.setStyleSheet(
            'color: white; font-size: 14px; font-weight: bold;'
        )
        hl.addWidget(title)
        outer.addWidget(header)

        # Filter fields 
        content = QWidget()
        content.setStyleSheet('background-color: white;')
        cl = QVBoxLayout(content)
        cl.setContentsMargins(14, 14, 14, 14)
        cl.setSpacing(10)

        cl.addWidget(self._field_label('Department'))
        self.dept_combo = QComboBox()
        self.dept_combo.addItem('All')
        self.dept_combo.addItems(sorted(self._df['Department'].dropna().unique()))
        self._style_combo(self.dept_combo)
        cl.addWidget(self.dept_combo)

        cl.addWidget(self._field_label('Job Role'))
        self.role_combo = QComboBox()
        self.role_combo.addItem('All')
        self.role_combo.addItems(sorted(self._df['Job_Role'].dropna().unique()))
        self._style_combo(self.role_combo)
        cl.addWidget(self.role_combo)

        cl.addWidget(self._field_label('Employment Status'))
        self.status_combo = QComboBox()
        self.status_combo.addItem('All')
        self.status_combo.addItems(['Active', 'Resigned', 'Terminated'])
        self._style_combo(self.status_combo)
        cl.addWidget(self.status_combo)

        cl.addWidget(self._field_label('Sex'))
        self.sex_combo = QComboBox()
        self.sex_combo.addItem('All')
        if 'Sex' in self._df.columns:
            self.sex_combo.addItems(sorted(self._df['Sex'].dropna().unique()))
        self._style_combo(self.sex_combo)
        cl.addWidget(self.sex_combo)

        cl.addWidget(self._field_label('Ethnicity'))
        self.ethnicity_combo = QComboBox()
        self.ethnicity_combo.addItem('All')
        if 'Ethnicity' in self._df.columns:
            self.ethnicity_combo.addItems(sorted(self._df['Ethnicity'].dropna().unique()))
        self._style_combo(self.ethnicity_combo)
        cl.addWidget(self.ethnicity_combo)

        cl.addWidget(self._field_label('Age Group'))
        self.age_group_combo = QComboBox()
        self.age_group_combo.addItem('All')
        if 'Age_Group' in self._df.columns:
            ordered = ['Under 30', '30–39', '40–49', '50–59', '60+']
            present = self._df['Age_Group'].dropna().unique()
            self.age_group_combo.addItems([g for g in ordered if g in present])
        self._style_combo(self.age_group_combo)
        cl.addWidget(self.age_group_combo)

        # Divider
        cl.addSpacing(4)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet('color: #E8E8E8;')
        cl.addWidget(divider)
        cl.addSpacing(4)

        cl.addWidget(self._field_label('Time Period'))
        self.period_mode_combo = QComboBox()
        self.period_mode_combo.addItems(analytics.PERIOD_MODES)
        self.period_mode_combo.setItemData(
            0, 'Everyone who worked here at any time in the range (standard headcount view)',
            Qt.ItemDataRole.ToolTipRole)
        self.period_mode_combo.setItemData(
            1, 'Only people whose hire date falls in the range (new-hire view)',
            Qt.ItemDataRole.ToolTipRole)
        self._style_combo(self.period_mode_combo)
        cl.addWidget(self.period_mode_combo)

        cl.addWidget(self._field_label('From'))
        self.date_from = QDateEdit(DEFAULT_HIRE_FROM)
        self.date_from.setCalendarPopup(True)
        theme.style_date_edit(self.date_from)
        cl.addWidget(self.date_from)

        cl.addWidget(self._field_label('To'))
        self.date_to = QDateEdit(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        theme.style_date_edit(self.date_to)
        cl.addWidget(self.date_to)

        cl.addStretch()
        # Scroll the fields on short screens so Apply / Reset stay visible
        fields_scroll = QScrollArea()
        fields_scroll.setWidgetResizable(True)
        fields_scroll.setFrameShape(QFrame.Shape.NoFrame)
        fields_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        fields_scroll.setWidget(content)
        outer.addWidget(fields_scroll, stretch=1)

        # Footer buttons 
        footer = QWidget()
        footer.setStyleSheet(
            'background-color: #F5F7FA;'
            ' border-top: 1px solid #E0E0E0;'
        )
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(14, 10, 14, 14)
        fl.setSpacing(8)

        apply_btn = QPushButton('Apply Filters')
        apply_btn.setFixedHeight(36)
        apply_btn.clicked.connect(self.emit_filters)
        self._apply_btn = apply_btn

        reset_btn = QPushButton('Reset Filters')
        reset_btn.setFixedHeight(34)
        reset_btn.setStyleSheet('''
            QPushButton {
                background-color: white; color: #555555;
                border-radius: 5px; font-size: 12px;
                border: 1px solid #CCCCCC;
            }
            QPushButton:hover { background-color: #F0F0F0; }
        ''')
        reset_btn.clicked.connect(self._reset)

        self._pending_hint = QLabel('Changes not applied yet')
        self._pending_hint.setStyleSheet('color: #B9770E; font-size: 11px; background: transparent; border: none;')
        self._pending_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pending_hint.hide()

        fl.addWidget(self._pending_hint)
        fl.addWidget(apply_btn)
        fl.addWidget(reset_btn)
        outer.addWidget(footer)

        # Watch every field so the Apply button can show when changes are waiting
        self._applied: dict | None = None
        for combo in self._combos().values():
            combo.currentIndexChanged.connect(self._update_pending)
        self.period_mode_combo.currentIndexChanged.connect(self._update_pending)
        self.date_from.dateChanged.connect(self._update_pending)
        self.date_to.dateChanged.connect(self._update_pending)
        self._update_pending()

    #  Helpers

    def _field_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(theme.LABEL_FIELD)
        return lbl

    def _style_combo(self, combo):
        combo.setStyleSheet(theme.COMBO_STYLE)


    def _combos(self) -> dict:
        # Sidebar filter key -> its dropdown
        return {
            'department': self.dept_combo, 'job_role': self.role_combo,
            'status': self.status_combo, 'sex': self.sex_combo,
            'ethnicity': self.ethnicity_combo, 'age_group': self.age_group_combo,
        }

    def _current(self) -> dict:
        f = {key: combo.currentText() for key, combo in self._combos().items()}
        f.update({
            'period_mode': self.period_mode_combo.currentText(),
            'date_from':   self.date_from.date().toPyDate(),
            'date_to':     self.date_to.date().toPyDate(),
        })
        return f

    def _update_pending(self, *_args):
        # Highlight Apply when the fields differ from what the dashboard is showing
        pending = self._applied is not None and self._current() != self._applied
        self._pending_hint.setVisible(pending)
        self._apply_btn.setText('Apply Changes' if pending else 'Apply Filters')
        colour, hover = ('#E67E22', '#CA6F1E') if pending else ('#1F3864', '#2E75B6')
        self._apply_btn.setStyleSheet(f'''
            QPushButton {{
                background-color: {colour}; color: white;
                border-radius: 5px; font-size: 13px; border: none;
            }}
            QPushButton:hover   {{ background-color: {hover}; }}
        ''')

    def clear_filter(self, key: str):
        # Reset one filter (from a chip's ✕ on the dashboard) and re-apply
        if key in self._combos():
            self._combos()[key].setCurrentIndex(0)
        self.emit_filters()

    def _reset(self):
        self.dept_combo.setCurrentIndex(0)
        self.role_combo.setCurrentIndex(0)
        self.status_combo.setCurrentIndex(0)
        self.sex_combo.setCurrentIndex(0)
        self.ethnicity_combo.setCurrentIndex(0)
        self.age_group_combo.setCurrentIndex(0)
        self.period_mode_combo.setCurrentIndex(0)
        self.date_from.setDate(DEFAULT_HIRE_FROM)
        self.date_to.setDate(QDate.currentDate())
        self.emit_filters()

    def emit_filters(self):
        self._applied = self._current()
        self._update_pending()
        self.filters_changed.emit(dict(self._applied))
