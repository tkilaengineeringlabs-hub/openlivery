"""Guided builder persistence and runtime permissions with mocked model discovery."""
import uuid

import pytest

from conftest import TestingSession
from test_ollama import server, MODEL, URL  # Reuse the HTTP transport fixture.
from app.models import Agency, Agent, AgentTool, Client, AgentQA
from app.services.tools.registry import load_custom_tool_specs


@pytest.fixture
def setup_builder(authenticated_client, server):
    client = authenticated_client
    business = client.post('/api/clients', json={'name': 'Builder business'}).json()
    assert client.put('/api/providers/ollama', json={'base_url': URL, 'name': 'Local'}).status_code == 200
    return client, business, server


def payload(business, **changes):
    return {'name': 'Receptionist', 'client_id': business['id'], 'apply_builder': True,
            'provider': 'ollama', 'model': MODEL, 'prompt_language': 'en', 'objectives': ['respond_questions', 'customer_support'],
            'selected_channels': ['widget'], 'selected_tools': ['knowledge'],
            'template_id': 'veterinary_receptionist', 'tone': 'friendly',
            'personality': 'Be clear.', 'welcome_message': 'Welcome to {{business}}', **changes}


def test_guided_agent_persists_configuration_and_prompt(setup_builder):
    client, business, _ = setup_builder
    expected = payload(business)
    result = client.post('/api/agents', json=expected)
    assert result.status_code == 201, result.text
    agent = client.get('/api/agents/' + result.json()['id']).json()
    for key, value in expected.items():
        if key != 'apply_builder':
            assert agent[key] == value
    assert agent['instructions']
    assert agent['knowledge_enabled'] and not agent['appointments_enabled']
    assert not agent['escalation_builtin_enabled']
    assert agent['channel_types'] == []
    assert client.get('/api/automations').json() == []
    prompt = client.get(f"/api/agents/{agent['id']}/prompt").json()['prompt']
    assert 'Welcome to Builder business' in prompt and 'Friendly' in prompt
    assert 'Be clear.' in prompt
    updated = client.patch(f"/api/agents/{agent['id']}", json={'objectives': ['sales']})
    assert updated.status_code == 200
    assert client.get('/api/agents').json()[0]['objectives'] == ['sales']


def test_unavailable_selected_model_does_not_create_agent(setup_builder):
    client, business, state = setup_builder
    state['models'] = []
    response = client.post('/api/agents', json=payload(business))
    assert response.status_code == 422
    assert client.get('/api/agents').json() == []


@pytest.mark.parametrize('changes', [
    {'selected_tools': ['google_calendar']}, {'selected_channels': ['amazon']},
    {'tone': 'invented'}, {'selected_tools': ['create_appointment']},
    {'selected_tools': ['check_appointment_availability', 'create_appointment', 'reschedule_appointment', 'cancel_appointment']},
])
def test_invalid_or_unavailable_choices_are_atomic(setup_builder, changes):
    client, business, _ = setup_builder
    assert client.post('/api/agents', json=payload(business, **changes)).status_code == 422
    assert client.get('/api/agents').json() == []


def add_tool(business_id, *, foreign=False, other_business=False, enabled=True):
    with TestingSession() as db:
        business = db.get(Client, uuid.UUID(business_id))
        agency_id = business.agency_id
        if foreign:
            agency = Agency(name='Foreign', slug='foreign')
            db.add(agency); db.flush()
            agency_id = agency.id
        if foreign or other_business:
            business = Client(agency_id=agency_id, name='Other business', portal_slug='other')
            db.add(business); db.flush()
        source = Agent(agency_id=agency_id, client_id=business.id, name='Source')
        db.add(source); db.flush()
        tool = AgentTool(agent_id=source.id, name='lookup_order', type='http', url='https://example.test', enabled=enabled)
        db.add(tool); db.commit()
        return str(tool.id), str(source.id), str(business.id)


def test_explicit_tool_grant_and_runtime_revocation(setup_builder):
    client, business, _ = setup_builder
    tool_id, source_id, _ = add_tool(business['id'])
    response = client.post('/api/agents', json=payload(business, shared_tool_ids=[tool_id]))
    assert response.status_code == 201, response.text
    target_id = response.json()['id']
    assert response.json()['shared_tool_ids'] == [tool_id]
    assert response.json()['custom_tool_names'] == ['lookup_order']
    with TestingSession() as db:
        target = db.get(Agent, uuid.UUID(target_id))
        assert [spec.name for spec in load_custom_tool_specs(db, target)] == ['lookup_order']
        original = db.get(AgentTool, uuid.UUID(tool_id))
        assert str(original.agent_id) == source_id
        original.enabled = False
        db.commit()
        assert load_custom_tool_specs(db, target) == []
    assert client.get(f'/api/agents/{target_id}').json()['custom_tool_names'] == []


@pytest.mark.parametrize('options', [{'foreign': True}, {'other_business': True}, {'enabled': False}])
def test_tools_denied_across_scopes_or_when_disabled(setup_builder, options):
    client, business, _ = setup_builder
    tool_id, _, other_id = add_tool(business['id'], **options)
    response = client.post('/api/agents', json=payload(business, shared_tool_ids=[tool_id]))
    assert response.status_code == 422
    if options.get('foreign'):
        assert client.get(f'/api/catalog/agent-configuration/{other_id}').status_code == 404
        assert client.post('/api/agents', json=payload({'id': other_id})).status_code == 400
    ctx = client.get(f"/api/catalog/agent-configuration/{business['id']}").json()
    assert all(item['id'] != tool_id for item in ctx['tools'])


def test_model_without_tools_preserves_configuration_for_chat(setup_builder):
    client, business, state = setup_builder
    tool_id, _, _ = add_tool(business['id'])
    state['capabilities'] = ['completion']
    response = client.post('/api/agents', json=payload(business, shared_tool_ids=[tool_id]))
    assert response.status_code in (200, 201)
    assert response.json()["provider"] == "ollama"


def test_legacy_agent_loads_and_unrelated_edits_preserve_runtime_flags(authenticated_client):
    client = authenticated_client
    business = client.post('/api/clients', json={'name': 'Legacy business'}).json()
    result = client.post('/api/agents', json={'name': 'Legacy', 'client_id': business['id'], 'instructions': 'Legacy instructions'})
    assert result.status_code == 201
    agent = result.json()
    assert agent['objectives'] == [] and agent['template_id'] is None
    assert agent['knowledge_enabled'] is True and agent['escalation_builtin_enabled'] is True
    result = client.patch(f"/api/agents/{agent['id']}", json={'name': 'Renamed'})
    assert result.json()['instructions'] == 'Legacy instructions'
    assert result.json()['knowledge_enabled'] is True
    assert result.json()['escalation_builtin_enabled'] is True


def test_knowledge_permission_is_applied_to_prompt(setup_builder):
    client, business, _ = setup_builder
    agent = client.post('/api/agents', json=payload(business)).json()
    with TestingSession() as db:
        db.add(AgentQA(agent_id=uuid.UUID(agent['id']), question='Secret FAQ', answer='Private answer'))
        db.commit()
    url = f"/api/agents/{agent['id']}"
    assert 'Private answer' in client.get(url + '/prompt').json()['prompt']
    assert client.patch(url, json={'selected_tools': []}).status_code == 200
    assert 'Private answer' not in client.get(url + '/prompt').json()['prompt']


def test_handoff_permission_can_be_saved_for_chat_only_model(setup_builder):
    client, business, state = setup_builder
    state['capabilities'] = ['completion']
    response = client.post('/api/agents', json=payload(business, objectives=['handoff_to_human'], selected_tools=['escalate_to_human']))
    assert response.status_code in (200, 201)
    assert response.json()["provider"] == "ollama"


def test_shared_grants_cannot_move_to_another_business(setup_builder):
    client, business, _ = setup_builder
    tool_id, _, _ = add_tool(business['id'])
    agent = client.post('/api/agents', json=payload(business, shared_tool_ids=[tool_id])).json()
    other = client.post('/api/clients', json={'name': 'Other owned business'}).json()
    response = client.patch('/api/agents/' + agent['id'], json={'client_id': other['id']})
    assert response.status_code == 422
    assert client.get('/api/agents/' + agent['id']).json()['client_id'] == business['id']


def test_guided_model_change_preserves_existing_own_tools(setup_builder):
    client, business, state = setup_builder
    _, source_id, _ = add_tool(business['id'])
    state['capabilities'] = ['completion']
    response = client.patch('/api/agents/' + source_id, json={'apply_builder': True, 'provider': 'ollama', 'model': MODEL})
    assert response.status_code in (200, 201)
    assert response.json()["provider"] == "ollama"
