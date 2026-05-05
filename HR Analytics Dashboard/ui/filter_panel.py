from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QDateEdit, QPushButton, QFrame,
)
from PyQt6.QtCore import pyqtSignal, QDate


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
            'color: white; font-size: 14px; font-weight: bold; font-family: Arial;'
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

        cl.addWidget(self._field_label('Hire Date From'))
        self.date_from = QDateEdit(QDate(2015, 1, 1))
        self.date_from.setCalendarPopup(True)
        self.date_from.setStyleSheet(self._date_style())
        cl.addWidget(self.date_from)

        cl.addWidget(self._field_label('Hire Date To'))
        self.date_to = QDateEdit(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        self.date_to.setStyleSheet(self._date_style())
        cl.addWidget(self.date_to)

        cl.addStretch()
        outer.addWidget(content, stretch=1)

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
        apply_btn.setStyleSheet('''
            QPushButton {
                background-color: #1F3864; color: white;
                border-radius: 5px; font-size: 13px; border: none;
            }
            QPushButton:hover   { background-color: #2E75B6; }
            QPushButton:pressed { background-color: #163060; }
        ''')
        apply_btn.clicked.connect(self._emit)

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

        fl.addWidget(apply_btn)
        fl.addWidget(reset_btn)
        outer.addWidget(footer)

    #  Helpers

    def _field_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            'font-size: 11px; font-weight: bold; color: #444444;'
        )
        return lbl

    def _style_combo(self, combo):
        combo.setStyleSheet('''
            QComboBox {
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                padding: 5px 8px;
                background: white;
                font-size: 12px;
                color: #333333;
            }
            QComboBox:focus { border-color: #2E75B6; }
            QComboBox::drop-down { border: none; }
        ''')

    def _date_style(self):
        return '''
            QDateEdit {
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 12px;
                color: #333333;
                background: white;
            }
            QDateEdit:focus { border-color: #2E75B6; }
        '''

    def _reset(self):
        self.dept_combo.setCurrentIndex(0)
        self.role_combo.setCurrentIndex(0)
        self.status_combo.setCurrentIndex(0)
        self.sex_combo.setCurrentIndex(0)
        self.ethnicity_combo.setCurrentIndex(0)
        self.age_group_combo.setCurrentIndex(0)
        self.date_from.setDate(QDate(2015, 1, 1))
        self.date_to.setDate(QDate.currentDate())
        self._emit()

    def _emit(self):
        self.filters_changed.emit({
            'department': self.dept_combo.currentText(),
            'job_role':   self.role_combo.currentText(),
            'status':     self.status_combo.currentText(),
            'sex':        self.sex_combo.currentText(),
            'ethnicity':  self.ethnicity_combo.currentText(),
            'age_group':  self.age_group_combo.currentText(),
            'date_from':  self.date_from.date().toPyDate(),
            'date_to':    self.date_to.date().toPyDate(),
        })
