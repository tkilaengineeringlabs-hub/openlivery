"""Phase 4 uses real domain services and disposable records; only model HTTP is mocked."""
import asyncio
import json
import uuid
from unittest.mock import Mock
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from conftest import TestingSession, customer_conversation
from app.models import Agent, AgentQA, Appointment, Conversation, ToolExecution
from app.services.tools.runner import run_completion
from app.services.tools.executor import ToolDispatcher, ToolExecutor, CURRENT_EXECUTOR
from app.services.tools.specs import ToolSpec
from test_appointments import setup, slots
from test_groq import server as groq_server, MODEL as GROQ_MODEL
from test_ollama import server as ollama_server, MODEL as OLLAMA_MODEL, URL


def agent_setup(client, provider='openai', model='gpt-4.1-mini', **extra):
    business = client.post('/api/clients', json={'name': 'Runtime business'}).json()
    agent = client.post('/api/agents', json={'client_id': business['id'], 'name': 'Runtime agent', 'provider': provider, 'model': model, **extra})
    assert agent.status_code == 201, agent.text
    return business, agent.json()


def run(client, agent, **kwargs):
    conversation = customer_conversation(client, agent['id'])
    response = client.post('/api/conversations/' + conversation['id'] + '/messages', json={'content': 'Execute request'})
    if response.status_code != 200:
        from fastapi import HTTPException
        raise HTTPException(response.status_code, response.json().get('detail'))
    message = response.json()['messages'][-1]
    return SimpleNamespace(text=message['content'], tool_calls=message.get('tool_calls')), conversation


def test_groq_real_booking_lifecycle_and_audit(authenticated_client, groq_server):
    client = authenticated_client
    groq_server['tools'] = True
    assert client.put('/api/providers/groq', json={'api_key': 'fixture'}).status_code == 200
    cid, sid, day = setup(client)
    times = slots(client, cid, sid, day)['slots']
    agent = client.post('/api/agents', json={'client_id': cid, 'name': 'Receptionist', 'provider': 'groq', 'model': GROQ_MODEL, 'appointments_enabled': True}).json()
    conversation = customer_conversation(client, agent['id'])
    def turn(name, args):
        groq_server['replies'] = [
            {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'call', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]},
            {'role': 'assistant', 'content': 'Confirmed from the actual tool result.'}]
        response = client.post('/api/conversations/' + conversation['id'] + '/messages', json={'content': 'Appointment request'})
        assert response.status_code == 200, response.text
        message = response.json()['messages'][-1]
        return SimpleNamespace(text=message['content'], tool_calls=message['tool_calls'])
    checked = turn('check_appointment_availability', {'service_id': sid, 'date': day})
    assert checked.tool_calls[0]['is_error'] is False
    created = turn('create_appointment', {'service_id': sid, 'starts_at': times[0]['starts_at'], 'customer_name': 'Synthetic customer', 'notes': 'Sensitive fixture notes'})
    assert created.tool_calls[0]['is_error'] is False
    with TestingSession() as db:
        appointment = db.scalar(select(Appointment))
        aid = str(appointment.id)
        assert appointment.source == 'agent' and appointment.conversation_id == uuid.UUID(conversation['id'])
    moved = turn('reschedule_appointment', {'appointment_id': aid, 'starts_at': times[4]['starts_at']})
    assert not moved.tool_calls[0]['is_error']
    cancelled = turn('cancel_appointment', {'appointment_id': aid})
    assert not cancelled.tool_calls[0]['is_error']
    with TestingSession() as db:
        assert db.get(Appointment, uuid.UUID(aid)).status == 'cancelled'
        rows = db.scalars(select(ToolExecution)).all()
        assert len(rows) == 4 and all(r.status == 'succeeded' for r in rows)
        assert 'Sensitive fixture notes' not in str([r.arguments for r in rows])
    log = client.get('/api/conversations/' + conversation['id'] + '/tool-executions')
    assert log.status_code == 200 and len(log.json()) == 4


def test_ollama_knowledge_search_and_business_isolation(authenticated_client, ollama_server):
    client = authenticated_client
    client.put('/api/providers/ollama', json={'base_url': URL})
    business, agent = agent_setup(client, 'ollama', OLLAMA_MODEL)
    _, other = agent_setup(client, 'ollama', OLLAMA_MODEL)
    with TestingSession() as db:
        db.add(AgentQA(agent_id=uuid.UUID(agent['id']), question='Business hours?', answer='Monday to Friday, 9 to 18.'))
        db.add(AgentQA(agent_id=uuid.UUID(other['id']), question='Business hours?', answer='Foreign business private answer'))
        db.commit()
    ollama_server['replies'] = [
        {'role': 'assistant', 'content': '', 'tool_calls': [{'function': {'name': 'knowledge_search', 'arguments': {'query': 'Business hours', 'limit': 2}}}]},
        {'role': 'assistant', 'content': 'Monday to Friday, 9 to 18.'}]
    result, conversation = run(client, agent)
    assert result.tool_calls[0]['is_error'] is False
    payload = json.loads(ollama_server['requests'][-1].content)
    assert 'Monday to Friday' in payload['messages'][-1]['content']
    assert 'Foreign business' not in payload['messages'][-1]['content']
    assert client.get('/api/conversations/' + conversation['id'] + '/tool-executions').json()[0]['status'] == 'succeeded'


def test_handoff_changes_real_conversation_and_inbox(authenticated_client, ollama_server):
    client = authenticated_client
    client.put('/api/providers/ollama', json={'base_url': URL})
    _, agent = agent_setup(client, 'ollama', OLLAMA_MODEL, escalation_builtin_enabled=True)
    ollama_server['replies'] = [
        {'role': 'assistant', 'content': '', 'tool_calls': [{'function': {'name': 'escalate_to_human', 'arguments': {'trigger': 'human_request', 'reason': 'Customer requested a person'}}}]},
        {'role': 'assistant', 'content': 'A person will continue.'}]
    result, conversation = run(client, agent)
    assert not result.tool_calls[0]['is_error']
    state = client.get('/api/conversations/' + conversation['id']).json()
    assert state['mode'] == 'human' and any(m.get('kind') == 'activity' for m in state['messages'])
    inbox = client.get('/api/conversations/inbox').json()
    assert any(c['id'] == conversation['id'] for c in inbox)


def test_denied_webhook_recovers_and_is_durable(authenticated_client, ollama_server):
    client = authenticated_client
    client.put('/api/providers/ollama', json={'base_url': URL})
    _, agent = agent_setup(client, 'ollama', OLLAMA_MODEL)
    ollama_server['replies'] = [
        {'role': 'assistant', 'content': '', 'tool_calls': [{'function': {'name': 'webhook_call', 'arguments': {'url': 'http://localhost:8000', 'token': 'secret-fixture'}}}]},
        {'role': 'assistant', 'content': 'The requested action is unavailable.'}]
    result, conversation = run(client, agent)
    assert result.text == 'The requested action is unavailable.' and result.tool_calls[0]['is_error']
    audit = client.get('/api/conversations/' + conversation['id'] + '/tool-executions').json()
    assert audit[0]['status'] == 'denied' and 'secret-fixture' not in json.dumps(audit)


def test_chat_only_model_does_not_receive_tools(authenticated_client, ollama_server):
    client = authenticated_client
    client.put('/api/providers/ollama', json={'base_url': URL})
    _, agent = agent_setup(client, 'ollama', OLLAMA_MODEL)
    ollama_server['capabilities'] = ['completion']
    result, _ = run(client, agent)
    assert result.text == 'OK'
    payload = json.loads(ollama_server['requests'][-1].content)
    assert 'tools' not in payload and 'Tools are unavailable' in payload['messages'][0]['content']


def test_schema_errors_and_permission_revocation_prevent_execution(authenticated_client):
    client = authenticated_client
    business, agent = agent_setup(client)
    tool = client.post('/api/agents/' + agent['id'] + '/tools', json={'type': 'http', 'name': 'allowed', 'url': 'https://example.test', 'http_method': 'POST', 'body_params': [{'name': 'quantity', 'type': 'integer', 'required': True}]}).json()
    from app.models import AgentTool
    from app.services.tools.specs import build_tool_specs
    with TestingSession() as db:
        row = db.get(AgentTool, uuid.UUID(tool['id']))
        spec = build_tool_specs([row])[0]
        spec.handler = Mock(return_value=('Executed', False))
        executor = ToolExecutor(db.get(Agent, uuid.UUID(agent['id'])).agency_id, uuid.UUID(business['id']), uuid.UUID(agent['id']), None, 'openai', 'gpt-4.1-mini')
        token = CURRENT_EXECUTOR.set(executor)
        try:
            dispatcher = ToolDispatcher([spec], 'openai')
            assert asyncio.run(dispatcher.call('allowed', {'quantity': 'bad'}))[1]
            row.enabled = False; db.commit()
            assert asyncio.run(dispatcher.call('allowed', {'quantity': 1}))[1]
            spec.handler.assert_not_called()
        finally:
            CURRENT_EXECUTOR.reset(token)


def test_five_executions_limit_shared_across_batch():
    handler = Mock(return_value=('OK', False))
    dispatcher = ToolDispatcher([ToolSpec('action', 'Action', {}, handler=handler)], 'groq')
    for _ in range(5):
        assert not asyncio.run(dispatcher.call('action', {}))[1]
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        asyncio.run(dispatcher.call('action', {}))
    assert handler.call_count == 5


def test_external_schema_references_cannot_trigger_network_requests():
    handler = Mock()
    dispatcher = ToolDispatcher([ToolSpec('action', 'Action', {'$ref': 'http://169.254.169.254/schema'}, handler=handler)], 'groq')
    assert asyncio.run(dispatcher.call('action', {}))[1]
    handler.assert_not_called()


def test_tool_failure_recovers_without_exposing_exception():
    handler = Mock(side_effect=RuntimeError('private-token-fixture'))
    dispatcher = ToolDispatcher([ToolSpec('action', 'Action', {}, handler=handler)], 'ollama')
    result, failed = asyncio.run(dispatcher.call('action', {}))
    assert failed and 'private-token-fixture' not in result


def test_webhook_private_destinations_fail_even_with_development_bypass(monkeypatch):
    from app.config import get_settings
    from app.services.tools.http_exec import _blocked_reason
    monkeypatch.setattr(get_settings(), 'tools_allow_private_urls', True)
    for url in ('http://127.0.0.1', 'http://169.254.169.254', 'http://10.0.0.1', 'http://[::1]'):
        assert _blocked_reason(url, allow_private=False) is not None


def test_audit_remains_when_model_fails_after_tool(authenticated_client, ollama_server):
    client = authenticated_client
    client.put('/api/providers/ollama', json={'base_url': URL})
    _, agent = agent_setup(client, 'ollama', OLLAMA_MODEL)
    ollama_server['replies'] = [
        {'role': 'assistant', 'content': '', 'tool_calls': [{'function': {'name': 'knowledge_search', 'arguments': {'query': 'hours'}}}]},
        {'role': 'assistant', 'content': ''}]
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        run(client, agent)
    with TestingSession() as db:
        assert db.scalar(select(ToolExecution)).status == 'succeeded'


def test_audit_endpoint_is_tenant_scoped(authenticated_client, ollama_server, monkeypatch):
    client = authenticated_client
    client.put('/api/providers/ollama', json={'base_url': URL})
    _, agent = agent_setup(client, 'ollama', OLLAMA_MODEL)
    ollama_server['replies'] = [
        {'role': 'assistant', 'content': '', 'tool_calls': [{'function': {'name': 'knowledge_search', 'arguments': {'query': 'hours'}}}]},
        {'role': 'assistant', 'content': 'No knowledge yet.'}]
    _, conversation = run(client, agent)
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), 'allow_multi_agency', True)
    client.post('/api/auth/logout')
    assert client.post('/api/auth/register', json={'agency_name': 'Other tenant', 'name': 'Other', 'email': 'other-runtime@example.com', 'password': 'fixture-password'}).status_code == 201
    assert client.get('/api/conversations/' + conversation['id'] + '/tool-executions').status_code == 404


def test_mcp_runtime_blocks_redirects_and_cross_origin_sse_endpoints(monkeypatch):
    import httpx
    from app.services.tools.mcp_client import runtime_http_client_factory
    from app.services.tools import http_exec
    monkeypatch.setattr(http_exec, '_blocked_reason', lambda url, **kwargs: None)
    client = runtime_http_client_factory('https://tools.example.test/mcp')()
    assert client.follow_redirects is False
    hook = client.event_hooks['request'][0]
    asyncio.run(hook(httpx.Request('POST', 'https://tools.example.test/messages')))
    with pytest.raises(httpx.HTTPError):
        asyncio.run(hook(httpx.Request('POST', 'http://127.0.0.1/messages')))
    with pytest.raises(httpx.HTTPError):
        asyncio.run(hook(httpx.Request('POST', 'https://other.example.test/messages')))
    asyncio.run(client.aclose())


def test_external_tools_redact_echoed_auth_headers():
    from app.services.tools.http_exec import redact_header_values
    assert 'fixture-token' not in redact_header_values('echo fixture-token', {'Authorization': 'Bearer fixture-token'})
    assert 'returned-secret' not in redact_header_values('{"data": {"access_token": "returned-secret"}}', {})


@pytest.mark.parametrize('url', ['https://{host}/webhook', 'https://user:credential@tools.example.test/webhook'])
def test_model_cannot_control_tool_authority_or_see_url_credentials(url):
    from app.schemas_tools import HttpToolIn
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        HttpToolIn(type='http', name='webhook', url=url)


def test_mismatched_business_conversation_is_rejected_before_credentials(authenticated_client, monkeypatch):
    client = authenticated_client
    _, original = agent_setup(client)
    _, other = agent_setup(client)
    conversation = customer_conversation(client, original['id'])
    with TestingSession() as db:
        row = db.get(Conversation, uuid.UUID(conversation['id']))
        row.agent_id = uuid.UUID(other['id'])
        db.commit()  # Deliberately corrupt only the disposable fixture.
    from app.routers import conversations
    credentials = Mock()
    monkeypatch.setattr(conversations, 'resolve_agent_credentials', credentials)
    response = client.post('/api/conversations/' + conversation['id'] + '/messages', json={'content': 'Private request'})
    assert response.status_code == 404
    credentials.assert_not_called()
