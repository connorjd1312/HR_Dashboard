from __future__ import annotations

import json
import os

from PyQt6.QtCore import QByteArray, QSettings

ORGANISATION = 'HRAnalytics'
APPLICATION = 'HRAnalyticsDashboard'

MAX_RECENT = 8
THEMES = ('light', 'dark', 'system')

SOURCE_DEFAULT = 'default'
SOURCE_FILES = 'files'


class AppSettings:

    def __init__(self, path: str | None = None):
        if path:
            self._s = QSettings(path, QSettings.Format.IniFormat)
        else:
            self._s = QSettings(ORGANISATION, APPLICATION)

    def _get_json(self, key: str, default):
        raw = self._s.value(key, None)
        if not isinstance(raw, str) or not raw:
            return default
        try:
            return json.loads(raw)
        except ValueError:
            return default

    def _set_json(self, key: str, value) -> None:
        self._s.setValue(key, json.dumps(value))

    def _get_int(self, key: str, default: int) -> int:
        try:
            return int(self._s.value(key, default))
        except (TypeError, ValueError):
            return default

    def _get_bool(self, key: str, default: bool) -> bool:
        v = self._s.value(key, default)
        if isinstance(v, str):
            return v.strip().lower() in ('true', '1', 'yes')
        return bool(v)

    def sync(self) -> None:
        self._s.sync()

    def clear(self) -> None:
        self._s.clear()
        self._s.sync()

    @property
    def theme(self) -> str:
        v = self._s.value('appearance/theme', 'light')
        return v if v in THEMES else 'light'

    @theme.setter
    def theme(self, value: str) -> None:
        if value in THEMES:
            self._s.setValue('appearance/theme', value)

    @property
    def geometry(self) -> QByteArray | None:
        v = self._s.value('window/geometry', None)
        return v if isinstance(v, QByteArray) and not v.isEmpty() else None

    @geometry.setter
    def geometry(self, value: QByteArray) -> None:
        self._s.setValue('window/geometry', value)

    @property
    def tab_index(self) -> int:
        return max(0, self._get_int('window/tab_index', 0))

    @tab_index.setter
    def tab_index(self, value: int) -> None:
        self._s.setValue('window/tab_index', int(value))

    @property
    def sidebar_width(self) -> int | None:
        w = self._get_int('window/sidebar_width', 0)
        return w if w > 0 else None

    @sidebar_width.setter
    def sidebar_width(self, value: int) -> None:
        self._s.setValue('window/sidebar_width', int(value))

    @property
    def reopen_last(self) -> bool:
        return self._get_bool('data/reopen_last', True)

    @reopen_last.setter
    def reopen_last(self, value: bool) -> None:
        self._s.setValue('data/reopen_last', bool(value))

    @property
    def last_source(self) -> str | None:
        v = self._s.value('data/last_source', None)
        return v if v in (SOURCE_DEFAULT, SOURCE_FILES) else None

    @property
    def last_paths(self) -> list[str]:
        paths = self._get_json('data/last_paths', [])
        return [p for p in paths if isinstance(p, str)] if isinstance(paths, list) else []

    def set_last_data(self, source: str | None, paths: list[str] | None = None) -> None:
        if source is None:
            self._s.remove('data/last_source')
            self._s.remove('data/last_paths')
            return
        self._s.setValue('data/last_source', source)
        self._set_json('data/last_paths', [os.path.abspath(p) for p in (paths or [])]
                       if source == SOURCE_FILES else [])

    @property
    def recent_files(self) -> list[str]:
        files = self._get_json('data/recent_files', [])
        return [p for p in files if isinstance(p, str)][:MAX_RECENT] if isinstance(files, list) else []

    def add_recent(self, paths: list[str]) -> None:
        recent = self.recent_files
        for p in reversed(paths):
            p = os.path.abspath(p)
            if p in recent:
                recent.remove(p)
            recent.insert(0, p)
        self._set_json('data/recent_files', recent[:MAX_RECENT])

    def remove_recent(self, path: str) -> None:
        self._set_json('data/recent_files', [p for p in self.recent_files if p != os.path.abspath(path)])

    def clear_recent(self) -> None:
        self._s.remove('data/recent_files')

    @property
    def report_dir(self) -> str | None:
        d = self._s.value('dirs/report', None)
        return d if isinstance(d, str) and os.path.isdir(d) else None

    @report_dir.setter
    def report_dir(self, value: str) -> None:
        self._s.setValue('dirs/report', value)

    @property
    def dashboard_layout(self) -> dict | None:
        v = self._get_json('dashboard/layout', None)
        return v if isinstance(v, dict) else None

    @dashboard_layout.setter
    def dashboard_layout(self, value: dict | None) -> None:
        if value is None:
            self._s.remove('dashboard/layout')
        else:
            self._set_json('dashboard/layout', value)
