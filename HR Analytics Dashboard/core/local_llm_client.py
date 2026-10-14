# Runs a local language model inside the app

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Callable

import requests

# Keep models next to the .exe so downloads are not lost
if getattr(sys, 'frozen', False):
    MODEL_DIR = Path(sys.executable).resolve().parent / 'models'
else:
    MODEL_DIR = Path(__file__).resolve().parent.parent / 'models'
MODEL_FILENAME = 'Llama-3.2-3B-Instruct-Q4_K_M.gguf'
MODEL_URL = (
    'https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/'
    + MODEL_FILENAME
)
DEFAULT_MODEL = 'Llama 3.2 3B (local)'  # display name shown in the UI's model list

# Model settings: all CPU cores, temperature 0, short replies
N_THREADS = max(1, os.cpu_count() or 1)
TEMPERATURE = 0.0
MAX_TOKENS_JSON = 200
MAX_TOKENS_TEXT = 350

ProgressCallback = Callable[[int, int], None]  # (bytes_downloaded, total_bytes)


class LocalLLMError(Exception):
    # Raised when the model fails to load, run or download
    pass


class LocalLLMClient:

    def __init__(self, model_dir: str | Path = MODEL_DIR):
        self.model_dir = Path(model_dir)
        self.model_path = self.model_dir / MODEL_FILENAME
        self._llm = None
        self._load_lock = threading.Lock()
        # One model is shared, so only one request runs at a time
        self._infer_lock = threading.Lock()

    def is_available(self) -> bool:
        # The model is ready if its file exists
        return self.model_path.exists() and self.model_path.stat().st_size > 0

    def list_models(self) -> list[str]:
        return [DEFAULT_MODEL] if self.is_available() else []

    def download_model(self, progress_cb: ProgressCallback | None = None) -> None:
        # Download to a .partial file, then rename it when done
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
                    'llama-cpp-python is not installed, run: pip install -r requirements.txt'
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
        # Load the model early so the first answer is faster
        self._ensure_loaded()

    def chat(
        self,
        model: str,
        messages: list[dict],
        json_mode: bool = False,
        timeout: float = 60.0,
        max_tokens: int | None = None,
    ) -> str:
        # model and timeout are unused, kept for compatibility
        self._ensure_loaded()

        kwargs = {
            'temperature': TEMPERATURE,
            'max_tokens': max_tokens or (MAX_TOKENS_JSON if json_mode else MAX_TOKENS_TEXT),
        }
        if json_mode:
            kwargs['response_format'] = {'type': 'json_object'}

        try:
            with self._infer_lock:
                resp = self._llm.create_chat_completion(messages=messages, **kwargs)
            content = resp['choices'][0]['message']['content']
        except LocalLLMError:
            raise
        except Exception as e:
            raise LocalLLMError(f'Local model inference failed: {e}') from e

        if not content or not content.strip():
            raise LocalLLMError('The local model returned an empty response.')

        return content
