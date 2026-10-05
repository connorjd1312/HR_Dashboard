# local_llm_client.py
# Embedded local LLM client — runs the model in-process via llama-cpp-python instead
# of talking to an external Ollama server. There is no separate process to install,
# start, or manage: the first run downloads one GGUF model file into models/, and every
# run after that loads it straight into this process's memory.
#
# No PyQt import here — this stays pure Python so it can run inside a QThread worker
# (ui/advisor_worker.py, ui/model_download_worker.py) and be exercised in tests without
# a Qt event loop or a real model file.

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

import requests

MODEL_DIR = Path(__file__).resolve().parent.parent / 'models'
MODEL_FILENAME = 'Llama-3.2-3B-Instruct-Q4_K_M.gguf'
MODEL_URL = (
    'https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/'
    + MODEL_FILENAME
)
DEFAULT_MODEL = 'Llama 3.2 3B (local)'  # display name shown in the UI's model list

# Inference settings (tuned with tools/advisor_eval.py)
# - all CPU cores: llama.cpp defaults to half of them
# - temperature 0: the same question always gets the same, most likely answer,
#   which keeps the model sticking to the figures it's given
# - token caps: router replies are a short JSON object; answers are a few sentences
N_THREADS = max(1, os.cpu_count() or 1)
TEMPERATURE = 0.0
MAX_TOKENS_JSON = 200
MAX_TOKENS_TEXT = 350

ProgressCallback = Callable[[int, int], None]  # (bytes_downloaded, total_bytes)


class LocalLLMError(Exception):
    # Raised for any failure loading or running the local model, or downloading it —
    # mirrors the old OllamaError so callers (query_router, advisor_worker) degrade
    # the same way: fall back to general_summary / show an error bubble.
    pass


class LocalLLMClient:

    def __init__(self, model_dir: str | Path = MODEL_DIR):
        self.model_dir = Path(model_dir)
        self.model_path = self.model_dir / MODEL_FILENAME
        self._llm = None
        self._load_lock = threading.Lock()

    def is_available(self) -> bool:
        # Model file present on disk == ready to use. No server to reach, so this is
        # just a filesystem check (kept as a method for interface parity with the
        # setup-card / recheck-button flow in forecasting_tab.py).
        return self.model_path.exists() and self.model_path.stat().st_size > 0

    def list_models(self) -> list[str]:
        return [DEFAULT_MODEL] if self.is_available() else []

    def download_model(self, progress_cb: ProgressCallback | None = None) -> None:
        # Streams the model to a .partial file and only renames it into place on
        # success, so a cancelled/failed download can never look like a valid model.
        self.model_dir.mkdir(parents=True, exist_ok=True)
        partial_path = self.model_path.with_suffix(self.model_path.suffix + '.partial')

        try:
            with requests.get(MODEL_URL, stream=True, timeout=30) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get('content-length', 0))
                downloaded = 0
                with open(partial_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb is not None:
                            progress_cb(downloaded, total)
        except requests.exceptions.RequestException as e:
            partial_path.unlink(missing_ok=True)
            raise LocalLLMError(f'Could not download the local model: {e}') from e

        os.replace(partial_path, self.model_path)

    def _ensure_loaded(self) -> None:
        if self._llm is not None:
            return
        with self._load_lock:
            if self._llm is not None:
                return
            if not self.is_available():
                raise LocalLLMError(
                    f'Local model not found at {self.model_path}. Download it first.'
                )
            try:
                from llama_cpp import Llama
            except ImportError as e:
                raise LocalLLMError(
                    'llama-cpp-python is not installed — run: pip install -r requirements.txt'
                ) from e
            try:
                self._llm = Llama(
                    model_path=str(self.model_path),
                    n_ctx=4096,
                    n_threads=N_THREADS,
                    n_threads_batch=N_THREADS,
                    verbose=False,
                )
            except Exception as e:
                raise LocalLLMError(f'Failed to load the local model: {e}') from e

    def warm_up(self) -> None:
        # Load the model ahead of the first question (it takes a while on CPU),
        # so the user's first answer isn't slowed down by loading.
        self._ensure_loaded()

    def chat(
        self,
        model: str,
        messages: list[dict],
        json_mode: bool = False,
        timeout: float = 60.0,
    ) -> str:
        # `model` and `timeout` are accepted for interface parity with the old
        # OllamaClient — there's only one bundled model and inference is a direct,
        # in-process call with no network timeout to apply.
        self._ensure_loaded()

        kwargs = {
            'temperature': TEMPERATURE,
            'max_tokens': MAX_TOKENS_JSON if json_mode else MAX_TOKENS_TEXT,
        }
        if json_mode:
            kwargs['response_format'] = {'type': 'json_object'}

        try:
            resp = self._llm.create_chat_completion(messages=messages, **kwargs)
            content = resp['choices'][0]['message']['content']
        except LocalLLMError:
            raise
        except Exception as e:
            raise LocalLLMError(f'Local model inference failed: {e}') from e

        if not content or not content.strip():
            raise LocalLLMError('The local model returned an empty response.')

        return content
