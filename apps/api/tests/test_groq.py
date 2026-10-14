"""Groq contracts with isolated HTTP fixtures; never use real credentials."""
import asyncio
import json
from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from conftest import TestingSession
from app.config import get_settings
from app.models import ProviderCredential
from app.services import groq
from app.services.model_providers import get_provider
from app.services.providers import resolve_provider_credentials
from app.services.tools.specs import ToolSpec

MODEL = "fixture-cloud-model"


@pytest.fixture
def server(monkeypatch):
    groq._TOOL_CAPABILITIES.clear()
    state = {"models": [MODEL], "requests": [], "content": "OK"}
    original = httpx.AsyncClient
    def respond(request):
        state["requests"].append(request)
        if state.get("exception"):
            raise state["exception"]
        if state.get("status"):
            return httpx.Response(state["status"], json={"error": {"message": "secret upstream detail"}})
        if request.url.path.endswith('/models'):
            return httpx.Response(200, json={"data": [{"id": m} for m in state["models"]]})
        payload = json.loads(request.content)
        message = {"role": "assistant", "content": state["content"]}
        if isinstance(payload.get("tool_choice"), dict) and state.get("tools"):
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": "probe", "type": "function", "function": {"name": "tkila_capability_check", "arguments": "{}"}}]}
        elif state.get("replies"):
            message = state['replies'].pop(0)
        return httpx.Response(200, json={"choices": [{"message": message}],
                                       "usage": {"prompt_tokens": 4, "completion_tokens": 1}})
    monkeypatch.setattr(groq.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    return state


def test_registration_models_connection_and_empty(server):
    provider = get_provider("groq")
    assert isinstance(provider, groq.GroqProvider)
    assert asyncio.run(provider.test_connection('', 'fixture'))['models'] == [MODEL]
    server['models'] = []
    assert asyncio.run(provider.list_models('', 'fixture')) == []
    assert provider.capabilities(MODEL).tools is None
    with pytest.raises(NotImplementedError):
        provider.stream()


@pytest.mark.parametrize('status,detail', [(401, 'unauthorized'), (403, 'unauthorized'), (429, 'rate_limit'), (500, 'unavailable'), (302, 'unavailable')])
def test_errors_are_safe(server, status, detail):
    server['status'] = status
    with pytest.raises(HTTPException) as caught:
        asyncio.run(get_provider('groq').test_connection('', 'fixture'))
    assert caught.value.detail == 'groq.' + detail
    assert len(server['requests']) == 1


@pytest.mark.parametrize('exception,detail', [(httpx.ReadTimeout('secret'), 'timeout'), (httpx.ConnectError('secret'), 'unavailable')])
def test_timeout_and_network(server, exception, detail):
    server['exception'] = exception
    with pytest.raises(HTTPException) as caught:
        asyncio.run(get_provider('groq').chat('', 'fixture', MODEL, []))
    assert caught.value.detail == 'groq.' + detail


def test_chat_history_usage_and_tools_fail_closed(server):
    provider = get_provider('groq')
    messages = [{'role': 'system', 'content': 'Business rules'}, {'role': 'user', 'content': 'OK'}]
    completion = asyncio.run(provider.chat('', 'fixture', MODEL, messages, temperature=0, max_tokens=42))
    assert (completion.text, completion.input_tokens, completion.output_tokens) == ('OK', 4, 1)
    payload = json.loads(server['requests'][-1].content)
    assert payload['messages'] == messages and payload['model'] == MODEL
    handler = Mock()
    with pytest.raises(HTTPException) as caught:
        asyncio.run(provider.chat('', 'fixture', MODEL, messages, tools=[ToolSpec('allowed', 'Action', {}, handler=handler)]))
    assert caught.value.detail == 'groq.tools_unconfirmed'
    handler.assert_not_called()
    server['content'] = None
    with pytest.raises(HTTPException) as caught:
        asyncio.run(provider.chat('', 'fixture', MODEL, messages))
    assert caught.value.detail == 'groq.invalid_response'


def test_saved_connection_runtime_and_isolation(authenticated_client, server, monkeypatch):
    client = authenticated_client
    result = client.put('/api/providers/groq', json={'api_key': 'fixture-secret', 'name': 'Groq test', 'default_model': MODEL})
    assert result.status_code == 200, result.text
    assert 'fixture-secret' not in result.text and result.json()['api_key_masked'] == ''
    assert client.post('/api/providers/groq/test').json()['models'] == [MODEL]
    assert client.get('/api/providers/groq/models').json()['models'] == [MODEL]
    assert client.post('/api/providers/groq/probe', json={'model': MODEL}).json()['ok'] is True
    with TestingSession() as db:
        row = db.scalar(select(ProviderCredential))
        assert row.encrypted_api_key != 'fixture-secret'
        monkeypatch.setattr(get_settings(), 'groq_api_key', 'fallback-secret')
        assert resolve_provider_credentials(db, row.agency_id, 'groq')[1] == 'fixture-secret'
    business = client.post('/api/clients', json={'name': 'Fixture business'}).json()
    agent = client.post('/api/agents', json={'name': 'Groq agent', 'client_id': business['id'], 'provider': 'groq', 'model': MODEL, 'instructions': 'Fixture rules'})
    assert agent.status_code == 201, agent.text
    conversation = client.post('/api/conversations', json={'agent_id': agent.json()['id']}).json()
    reply = client.post('/api/conversations/' + conversation['id'] + '/messages', json={'content': 'Responde únicamente con: OK'})
    assert reply.status_code == 200, reply.text
    assert reply.json()['messages'][-1]['content'] == 'OK'
    assert 'Fixture rules' in json.loads(server['requests'][-1].content)['messages'][0]['content']
    assert client.patch('/api/agents/' + agent.json()['id'], json={'model': 'missing'}).status_code == 422
    monkeypatch.setattr(get_settings(), 'groq_api_key', '')
    monkeypatch.setattr(get_settings(), 'allow_multi_agency', True)
    client.post('/api/auth/logout')
    assert client.post('/api/auth/register', json={'agency_name': 'Other', 'name': 'Other', 'email': 'other-groq@example.com', 'password': 'fixture-password'}).status_code == 201
    assert client.post('/api/providers/groq/test').status_code == 422
    assert client.patch('/api/agents/' + agent.json()['id'], json={'provider': 'groq'}).status_code == 404


@pytest.mark.parametrize('data', [[], {}, {'data': None}, {'data': [{}]}, {'data': ['bad']}])
def test_invalid_models(monkeypatch, data):
    original = httpx.AsyncClient
    monkeypatch.setattr(groq.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=data)), **kwargs))
    with pytest.raises(HTTPException) as caught:
        asyncio.run(get_provider('groq').list_models('', 'fixture'))
    assert caught.value.detail == 'groq.invalid_response'


def test_global_fallback_and_saved_priority(authenticated_client, server, monkeypatch):
    client = authenticated_client
    monkeypatch.setattr(get_settings(), 'groq_api_key', 'global-fixture')
    row = next(p for p in client.get('/api/providers').json() if p['provider'] == 'groq')
    assert row['configured'] is True and 'global-fixture' not in client.get('/api/providers').text
    assert client.post('/api/providers/groq/test').status_code == 200
    assert server['requests'][-1].headers['authorization'] == 'Bearer global-fixture'
    assert client.put('/api/providers/groq', json={'api_key': 'agency-fixture', 'name': 'Saved'}).status_code == 200
    assert client.post('/api/providers/groq/test').status_code == 200
    assert server['requests'][-1].headers['authorization'] == 'Bearer agency-fixture'
    assert client.put('/api/providers/groq', json={'api_key': ''}).status_code == 422
    assert client.delete('/api/providers/groq').status_code == 204
    assert client.post('/api/providers/groq/test').status_code == 200
    assert server['requests'][-1].headers['authorization'] == 'Bearer global-fixture'


def test_confirmed_tools_use_existing_executor_and_allowlist(server):
    server['tools'] = True
    provider = get_provider('groq')
    assert asyncio.run(provider.model_capabilities('', 'fixture', MODEL)).tools is True
    handler = Mock(return_value=('actual fixture result', False))
    server['replies'] = [
        {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'denied', 'type': 'function', 'function': {'name': 'foreign', 'arguments': '{}'}},
            {'id': 'allowed', 'type': 'function', 'function': {'name': 'allowed', 'arguments': '{"value": 1}'}}]},
        {'role': 'assistant', 'content': 'Done'},
    ]
    result = asyncio.run(provider.chat('', 'fixture', MODEL, [{'role': 'user', 'content': 'Use tools'}],
        tools=[ToolSpec('allowed', 'Action', {'type': 'object'}, handler=handler)]))
    handler.assert_called_once_with({'value': 1})
    assert result.text == 'Done'
    assert result.tool_calls[0]['is_error'] is True
    assert result.tool_calls[1]['is_error'] is False
    payload = json.loads(server['requests'][-1].content)
    assert payload['messages'][-1] == {'role': 'tool', 'tool_call_id': 'allowed', 'content': 'actual fixture result'}
    # Another credential must confirm capability independently.
    server['tools'] = False
    assert asyncio.run(provider.model_capabilities('', 'other-key', MODEL)).tools is None


def test_tool_loop_is_bounded_and_invalid_arguments_are_denied(server):
    server['tools'] = True
    call = {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': 'call', 'type': 'function', 'function': {'name': 'allowed', 'arguments': '[]'}}]}
    server['replies'] = [call] * 6
    handler = Mock()
    with pytest.raises(HTTPException) as caught:
        asyncio.run(get_provider('groq').chat('', 'fixture', MODEL, [], tools=[ToolSpec('allowed', 'Action', {}, handler=handler)]))
    assert caught.value.detail == 'groq.tool_limit'
    handler.assert_not_called()
    payloads = [json.loads(r.content) for r in server['requests'] if r.method == 'POST']
    assert len(payloads) == 7  # One capability check and six bounded chat requests.
    assert payloads[-1]['tool_choice'] == 'none'
