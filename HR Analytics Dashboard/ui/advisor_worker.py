# advisor_worker.py
# Runs the AI Workforce Advisor pipeline (route -> execute -> build context -> explain)
# on a background QThread so a slow/unreachable local LLM never freezes the UI.
# Qt signals marshal safely across threads, so the tab just connects to these and
# updates widgets on the main thread as usual.

from __future__ import annotations

import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal

from core import context_builder, query_router
from core.ollama_client import OllamaClient, OllamaError


class AdvisorWorker(QThread):
    stage = pyqtSignal(str)
    succeeded = pyqtSignal(str, dict)   # answer text, debug info (function + params)
    failed = pyqtSignal(str)

    def __init__(self, client: OllamaClient, model: str, question: str, df: pd.DataFrame, parent=None):
        super().__init__(parent)
        self._client = client
        self._model = model
        self._question = question
        self._df = df

    def run(self):
        try:
            self.stage.emit('Understanding your question…')
            route = query_router.route_query(self._client, self._model, self._question, self._df)

            self.stage.emit('Running analytics…')
            result = query_router.execute(route, self._df)
            context = context_builder.build_context(
                self._question, route.function, route.params, result,
            )

            self.stage.emit('Generating response…')
            answer = query_router.explain_result(self._client, self._model, self._question, context)

            self.succeeded.emit(answer, {'function': route.function, 'params': route.params})
        except OllamaError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f'Something went wrong answering that question: {e}')
