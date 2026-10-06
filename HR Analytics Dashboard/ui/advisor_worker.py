# advisor_worker.py
# Runs the AI Workforce Advisor pipeline (route -> execute -> build context -> explain)
# on a background QThread so a slow/unreachable local LLM never freezes the UI.
# Qt signals marshal safely across threads, so the tab just connects to these and
# updates widgets on the main thread as usual.

from __future__ import annotations

import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal

from core import context_builder, query_router
from core.local_llm_client import LocalLLMClient, LocalLLMError


class AdvisorWorker(QThread):
    stage = pyqtSignal(str)
    succeeded = pyqtSignal(str, dict)   # answer text, debug info (function + params)
    failed = pyqtSignal(str)

    def __init__(self, client: LocalLLMClient, model: str, question: str, df: pd.DataFrame,
                 history_df: pd.DataFrame | None = None, scope: str | None = None, parent=None):
        super().__init__(parent)
        self._client = client
        self._model = model
        self._question = question
        self._df = df                    # employees to answer about (maybe dashboard-filtered)
        self._history_df = history_df    # full data for trends / forecasts
        self._scope = scope              # description of the dashboard filters, if used

    def run(self):
        try:
            self.stage.emit('Understanding your question…')
            route = query_router.route_query(self._client, self._model, self._question, self._df)

            self.stage.emit('Looking up the data…')
            result = query_router.execute(route, self._df, self._history_df)
            used_df = (self._history_df if route.function in query_router.TIME_BASED_FUNCTIONS
                       and self._history_df is not None else self._df)
            debug = {'function': route.function, 'params': route.params,
                     'source': query_router.source_note(
                         route, used_df, None if used_df is self._history_df else self._scope)}

            # Exact answers (single KPIs, unsupported questions) skip the LLM entirely
            answer = query_router.direct_answer(route, result)
            if answer is None:
                context = context_builder.build_context(
                    self._question, route.function, route.params, result,
                )
                self.stage.emit('Writing the answer…')
                answer = query_router.explain_result(self._client, self._model, self._question, context)

            self.succeeded.emit(answer, debug)
        except LocalLLMError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f'Something went wrong answering that question: {e}')
