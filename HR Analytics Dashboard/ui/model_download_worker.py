# model_download_worker.py
# Downloads the bundled local LLM's weights on a background QThread, so the one-time
# multi-GB fetch never freezes the UI. Mirrors ui/advisor_worker.py's pattern of doing
# the real work off-thread and marshalling results back via Qt signals.

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from core.local_llm_client import LocalLLMClient, LocalLLMError


class ModelDownloadWorker(QThread):
    progress = pyqtSignal(int, int)  # bytes_downloaded, total_bytes
    succeeded = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, client: LocalLLMClient, parent=None):
        super().__init__(parent)
        self._client = client

    def run(self):
        try:
            self._client.download_model(progress_cb=self.progress.emit)
            self.succeeded.emit()
        except LocalLLMError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f'Download failed: {e}')
