# ollama_client.py
# Thin wrapper around Ollama's local REST API (https://github.com/ollama/ollama/blob/main/docs/api.md).
# No PyQt import here — this stays pure Python so it can run inside a QThread worker
# (ui/advisor_worker.py) and be exercised in tests without a Qt event loop.

from __future__ import annotations

import requests

DEFAULT_HOST = 'http://localhost:11434'
DEFAULT_MODEL = 'llama3.2'


class OllamaError(Exception):
    # Raised for any failure talking to Ollama — connection refused, timeout,
    # non-200 response, or a response missing the expected fields.
    pass


class OllamaClient:

    def __init__(self, host: str = DEFAULT_HOST):
        self.host = host.rstrip('/')

    def is_available(self, timeout: float = 1.5) -> bool:
        # Cheap reachability check used to decide whether to show the chat UI
        # or the "Ollama not detected" setup card.
        try:
            resp = requests.get(f'{self.host}/api/tags', timeout=timeout)
            return resp.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def list_models(self, timeout: float = 3.0) -> list[str]:
        try:
            resp = requests.get(f'{self.host}/api/tags', timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            return [m['name'] for m in data.get('models', [])]
        except requests.exceptions.RequestException as e:
            raise OllamaError(f'Could not reach Ollama at {self.host}: {e}') from e
        except (ValueError, KeyError) as e:
            raise OllamaError(f'Unexpected response from Ollama: {e}') from e

    def chat(
        self,
        model: str,
        messages: list[dict],
        json_mode: bool = False,
        timeout: float = 60.0,
    ) -> str:
        # Non-streaming chat completion. Returns the assistant message content.
        payload = {
            'model': model,
            'messages': messages,
            'stream': False,
        }
        if json_mode:
            payload['format'] = 'json'

        try:
            resp = requests.post(f'{self.host}/api/chat', json=payload, timeout=timeout)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise OllamaError(f'Could not reach Ollama at {self.host}: {e}') from e

        try:
            data = resp.json()
            content = data['message']['content']
        except (ValueError, KeyError) as e:
            raise OllamaError(f'Unexpected response from Ollama: {e}') from e

        if not content or not content.strip():
            raise OllamaError('Ollama returned an empty response.')

        return content
