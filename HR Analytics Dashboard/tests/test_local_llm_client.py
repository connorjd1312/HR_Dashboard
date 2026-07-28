import sys
import types
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from core.local_llm_client import LocalLLMClient, LocalLLMError, MODEL_FILENAME


# is_available / list_models — pure filesystem checks, no server to reach


def test_is_available_false_when_model_missing(tmp_path):
    client = LocalLLMClient(model_dir=tmp_path)
    assert client.is_available() is False


def test_is_available_true_when_model_present(tmp_path):
    (tmp_path / MODEL_FILENAME).write_bytes(b'weights')
    client = LocalLLMClient(model_dir=tmp_path)
    assert client.is_available() is True


def test_is_available_false_for_empty_file(tmp_path):
    (tmp_path / MODEL_FILENAME).write_bytes(b'')
    client = LocalLLMClient(model_dir=tmp_path)
    assert client.is_available() is False


def test_list_models_empty_when_not_downloaded(tmp_path):
    client = LocalLLMClient(model_dir=tmp_path)
    assert client.list_models() == []


def test_list_models_has_one_entry_when_downloaded(tmp_path):
    (tmp_path / MODEL_FILENAME).write_bytes(b'weights')
    client = LocalLLMClient(model_dir=tmp_path)
    assert len(client.list_models()) == 1


# download_model — streams to a .partial file, only renames into place on success


def _fake_stream_response(chunks: list[bytes], content_length: str = '10'):
    resp = MagicMock()
    resp.__enter__.return_value = resp
    resp.raise_for_status = Mock()
    resp.headers = {'content-length': content_length}
    resp.iter_content = Mock(return_value=iter(chunks))
    return resp


def test_download_model_writes_file_and_reports_progress(tmp_path):
    client = LocalLLMClient(model_dir=tmp_path)
    progress_calls = []

    with patch('core.local_llm_client.requests.get', return_value=_fake_stream_response([b'abc', b'def'])):
        client.download_model(progress_cb=lambda done, total: progress_calls.append((done, total)))

    assert client.model_path.read_bytes() == b'abcdef'
    assert progress_calls == [(3, 10), (6, 10)]
    assert not client.model_path.with_suffix(client.model_path.suffix + '.partial').exists()


def test_download_model_raises_local_llm_error_on_network_failure(tmp_path):
    client = LocalLLMClient(model_dir=tmp_path)
    with patch('core.local_llm_client.requests.get', side_effect=requests.exceptions.ConnectionError()):
        with pytest.raises(LocalLLMError):
            client.download_model()
    assert not client.model_path.exists()


# chat — lazy-loads a llama_cpp.Llama instance from the downloaded model file


def _install_fake_llama_cpp(monkeypatch, create_chat_completion_return):
    fake_instance = MagicMock()
    fake_instance.create_chat_completion.return_value = create_chat_completion_return
    fake_module = types.ModuleType('llama_cpp')
    fake_module.Llama = MagicMock(return_value=fake_instance)
    monkeypatch.setitem(sys.modules, 'llama_cpp', fake_module)
    return fake_module.Llama, fake_instance


def test_chat_raises_when_model_not_downloaded(tmp_path):
    client = LocalLLMClient(model_dir=tmp_path)
    with pytest.raises(LocalLLMError):
        client.chat('model', [{'role': 'user', 'content': 'hi'}])


def test_chat_returns_message_content(tmp_path, monkeypatch):
    (tmp_path / MODEL_FILENAME).write_bytes(b'weights')
    client = LocalLLMClient(model_dir=tmp_path)
    _install_fake_llama_cpp(monkeypatch, {'choices': [{'message': {'content': 'hello there'}}]})

    result = client.chat('model', [{'role': 'user', 'content': 'hi'}])

    assert result == 'hello there'


def test_chat_sets_json_response_format_when_requested(tmp_path, monkeypatch):
    (tmp_path / MODEL_FILENAME).write_bytes(b'weights')
    client = LocalLLMClient(model_dir=tmp_path)
    _, fake_instance = _install_fake_llama_cpp(monkeypatch, {'choices': [{'message': {'content': '{}'}}]})

    client.chat('model', [], json_mode=True)

    kwargs = fake_instance.create_chat_completion.call_args.kwargs
    assert kwargs['response_format'] == {'type': 'json_object'}


def test_chat_raises_on_empty_content(tmp_path, monkeypatch):
    (tmp_path / MODEL_FILENAME).write_bytes(b'weights')
    client = LocalLLMClient(model_dir=tmp_path)
    _install_fake_llama_cpp(monkeypatch, {'choices': [{'message': {'content': '   '}}]})

    with pytest.raises(LocalLLMError):
        client.chat('model', [])


def test_chat_wraps_inference_failure(tmp_path, monkeypatch):
    (tmp_path / MODEL_FILENAME).write_bytes(b'weights')
    client = LocalLLMClient(model_dir=tmp_path)
    _, fake_instance = _install_fake_llama_cpp(monkeypatch, None)
    fake_instance.create_chat_completion.side_effect = RuntimeError('boom')

    with pytest.raises(LocalLLMError):
        client.chat('model', [])


def test_chat_loads_model_only_once(tmp_path, monkeypatch):
    (tmp_path / MODEL_FILENAME).write_bytes(b'weights')
    client = LocalLLMClient(model_dir=tmp_path)
    fake_llama_cls, _ = _install_fake_llama_cpp(monkeypatch, {'choices': [{'message': {'content': 'ok'}}]})

    client.chat('model', [])
    client.chat('model', [])

    assert fake_llama_cls.call_count == 1
