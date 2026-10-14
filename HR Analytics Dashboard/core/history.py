from __future__ import annotations

import copy
from typing import Any

DEFAULT_LIMIT = 100


class History:

    def __init__(self, initial_state: Any = None, limit: int = DEFAULT_LIMIT):
        self._limit = max(2, limit)
        self._entries: list[tuple[str, Any]] = []
        self._pos = -1
        if initial_state is not None:
            self.reset(initial_state)

    def reset(self, state: Any, label: str = 'Start') -> None:
        self._entries = [(label, copy.deepcopy(state))]
        self._pos = 0

    def push(self, state: Any, label: str) -> bool:
        if self._pos < 0:
            self.reset(state)
            return True
        if state == self._entries[self._pos][1]:
            return False
        del self._entries[self._pos + 1:]
        self._entries.append((label, copy.deepcopy(state)))
        if len(self._entries) > self._limit:
            del self._entries[0]
        self._pos = len(self._entries) - 1
        return True

    def undo(self) -> Any | None:
        if not self.can_undo():
            return None
        self._pos -= 1
        return copy.deepcopy(self._entries[self._pos][1])

    def redo(self) -> Any | None:
        if not self.can_redo():
            return None
        self._pos += 1
        return copy.deepcopy(self._entries[self._pos][1])

    def can_undo(self) -> bool:
        return self._pos > 0

    def can_redo(self) -> bool:
        return 0 <= self._pos < len(self._entries) - 1

    def undo_label(self) -> str:
        return self._entries[self._pos][0] if self.can_undo() else ''

    def redo_label(self) -> str:
        return self._entries[self._pos + 1][0] if self.can_redo() else ''

    def current(self) -> Any | None:
        return copy.deepcopy(self._entries[self._pos][1]) if self._pos >= 0 else None

    def __len__(self) -> int:
        return len(self._entries)
