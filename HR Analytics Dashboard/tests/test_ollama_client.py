from unittest.mock import Mock, patch

import pytest
import requests

from core.ollama_client import OllamaClient, OllamaError


def test_is_available_true_on_200():
    client = OllamaClient()
    with patch('core.ollama_client.requests.get', return_value=Mock(status_code=200)):
        assert client.is_available() is True


def test_is_available_false_on_non_200():
    client = OllamaClient()
    with patch('core.ollama_client.requests.get', return_value=Mock(status_code=500)):
        assert client.is_available() is False


def test_is_available_false_on_connection_error():
    client = OllamaClient()
    with patch('core.ollama_client.requests.get', side_effect=requests.exceptions.ConnectionError()):
        assert client.is_available() is False


def test_list_models_parses_names():
    client = OllamaClient()
    resp = Mock(status_code=200)
    resp.raise_for_status = Mock()
    resp.json.return_value = {'models': [{'name': 'llama3.2'}, {'name': 'mistral'}]}
    with patch('core.ollama_client.requests.get', return_value=resp):
        assert client.list_models() == ['llama3.2', 'mistral']


def test_list_models_raises_ollama_error_when_unreachable():
    client = OllamaClient()
    with patch('core.ollama_client.requests.get', side_effect=requests.exceptions.ConnectionError()):
        with pytest.raises(OllamaError):
            client.list_models()


def test_chat_returns_message_content():
    client = OllamaClient()
    resp = Mock(status_code=200)
    resp.raise_for_status = Mock()
    resp.json.return_value = {'message': {'content': 'hello there'}}
    with patch('core.ollama_client.requests.post', return_value=resp) as mock_post:
        result = client.chat('llama3.2', [{'role': 'user', 'content': 'hi'}])

    assert result == 'hello there'
    payload = mock_post.call_args.kwargs['json']
    assert payload['model'] == 'llama3.2'
    assert payload['stream'] is False
    assert 'format' not in payload


def test_chat_sets_json_format_when_requested():
    client = OllamaClient()
    resp = Mock(status_code=200)
    resp.raise_for_status = Mock()
    resp.json.return_value = {'message': {'content': '{}'}}
    with patch('core.ollama_client.requests.post', return_value=resp) as mock_post:
        client.chat('llama3.2', [], json_mode=True)

    assert mock_post.call_args.kwargs['json']['format'] == 'json'


def test_chat_raises_on_empty_content():
    client = OllamaClient()
    resp = Mock(status_code=200)
    resp.raise_for_status = Mock()
    resp.json.return_value = {'message': {'content': '   '}}
    with patch('core.ollama_client.requests.post', return_value=resp):
        with pytest.raises(OllamaError):
            client.chat('llama3.2', [])


def test_chat_raises_ollama_error_on_network_failure():
    client = OllamaClient()
    with patch('core.ollama_client.requests.post', side_effect=requests.exceptions.Timeout()):
        with pytest.raises(OllamaError):
            client.chat('llama3.2', [])
