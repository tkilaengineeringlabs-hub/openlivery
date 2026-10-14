"""Template recommendation/application contracts over disposable tenant data."""
from dataclasses import replace

from conftest import TestingSession
from app.models import Agency, Client
from app.services.agent_catalog.templates import TEMPLATES, AUTOMATIONS, matches, validated_definition
from app.services.agent_catalog.objectives import OBJECTIVES
from app.services.agent_catalog.capabilities import TOOLS


def business(client, **changes):
    response = client.post('/api/clients', json={'name': 'Fixture veterinary', 'industry': 'health_wellness', 'business_type': 'veterinary', **changes})
    assert response.status_code == 201, response.text
    return response.json()


def preview(client, item, template='veterinary_receptionist'):
    response = client.get(f"/api/catalog/agent-templates/{item['id']}/{template}/preview?language=es")
    assert response.status_code == 200, response.text
    return response.json()


def test_registry_covers_ten_businesses_and_six_universal_templates():
    assert len(TEMPLATES) == 46 and len({t.id for t in TEMPLATES}) == 46
    assert sum(t.industry == 'other' for t in TEMPLATES) == 6
    for template in TEMPLATES:
        assert set(template.objectives) <= {o.id for o in OBJECTIVES}
        assert set(template.recommended_tools) <= {t.id for t in TOOLS}
        assert set(template.suggested_automations) <= AUTOMATIONS
        assert template.description.en and template.description.es
        assert template.version == 1


def test_industry_business_and_objective_matching_is_explainable():
    rows = matches('health_wellness', 'veterinary', ['customer_support', 'book_appointment', 'follow_up'], ['whatsapp'], ['knowledge'])
    assert rows[0]['template']['id'] == 'veterinary_receptionist'
    assert rows[0]['exact_match']
    assert rows[0]['score'] == sum(rows[0]['reasons'].values())
    rows = matches('retail_ecommerce', 'online_store', ['order_lookup'])
    assert rows[0]['template']['industry'] == 'retail_ecommerce'
    assert all('order_lookup' not in row['template']['objectives'] for row in rows)  # No order connector is available.
    rows = matches('automotive', 'workshop', ['lead_qualification', 'sales'])
    assert rows[0]['template']['id'] == 'automotive_quote'
    assert any(row['recommended'] and row['template']['industry'] == 'other' for row in matches('unlisted', 'other', []))


def test_recommendations_are_scoped_and_use_real_capabilities(authenticated_client):
    item = business(authenticated_client)
    response = authenticated_client.post(f"/api/catalog/agent-templates/{item['id']}/recommendations", json={'objectives': ['book_appointment', 'follow_up'], 'channels': ['widget']})
    assert response.status_code == 200
    first = response.json()[0]
    assert first['template']['id'] == 'veterinary_receptionist'
    assert first['reasons']['channels'] > 0
    assert first['reasons']['tools'] == 4  # Knowledge and handoff; calendar not configured.
    assert authenticated_client.post(f"/api/catalog/agent-templates/{item['id']}/recommendations", json={'objectives': ['invented']}).status_code == 422


def test_preview_missing_integration_does_not_provision(authenticated_client):
    item = business(authenticated_client)
    data = preview(authenticated_client, item)
    assert data['defaults']['selected_tools'] == ['knowledge', 'escalate_to_human']
    assert 'create_appointment' in data['unavailable_tools']
    assert not data['google_connected']
    assert 'hours' in data['missing_business_fields']
    assert {'confirmation', 'reminder24', 'reminder2', 'afterAppointment'} <= set(data['template']['suggested_automations'])
    assert authenticated_client.get('/api/agents').json() == []
    assert authenticated_client.get('/api/automations').json() == []


def test_explicit_apply_copies_defaults_and_preserves_edits(authenticated_client, monkeypatch):
    from app.services.agent_catalog import templates
    item = business(authenticated_client)
    response = authenticated_client.post('/api/agents', json={'client_id': item['id'], 'name': 'My receptionist', 'template_id': 'veterinary_receptionist', 'apply_template': True, 'prompt_language': 'es'})
    assert response.status_code == 201, response.text
    agent = response.json()
    assert agent['template_version'] == 1
    assert agent['name'] == 'My receptionist'
    assert agent['tone'] == 'friendly'
    assert agent['knowledge_enabled'] and agent['escalation_builtin_enabled']
    assert not agent['appointments_enabled']
    assert 'Fixture veterinary' in agent['instructions'] and '{{business_name}}' not in agent['instructions']
    url = f"/api/agents/{agent['id']}"
    custom = {'name': 'Edited', 'instructions': 'Only my custom instructions', 'objectives': ['sales'], 'tone': 'direct', 'selected_channels': ['instagram'], 'selected_tools': ['knowledge']}
    assert authenticated_client.patch(url, json=custom).status_code == 200
    monkeypatch.setitem(templates._BY_ID, 'veterinary_receptionist', replace(templates._BY_ID['veterinary_receptionist'], version=2, name=templates.Label('Changed', 'Cambiado')))
    loaded = authenticated_client.get(url).json()
    for key, value in custom.items():
        assert loaded[key] == value
    assert loaded['template_version'] == 1
    assert loaded['template_snapshot']['name']['es'] == 'Recepcionista veterinaria'
    assert authenticated_client.get('/api/automations').json() == []
    assert authenticated_client.get(url + '/tools').json() == []
    prompt = authenticated_client.get(url + '/prompt').json()['prompt']
    assert custom['instructions'] in prompt


def test_existing_custom_agent_unchanged_and_template_can_be_cleared(authenticated_client):
    item = business(authenticated_client)
    agent = authenticated_client.post('/api/agents', json={'client_id': item['id'], 'name': 'Legacy', 'instructions': 'Preserved'}).json()
    url = f"/api/agents/{agent['id']}"
    assert agent['template_id'] is None and agent['template_version'] is None and agent['template_snapshot'] is None
    preview(authenticated_client, item)
    assert authenticated_client.get(url).json() == agent
    response = authenticated_client.patch(url, json={'template_id': 'ecommerce_assistant', 'apply_template': True})
    assert response.status_code == 200, response.text
    applied = response.json()
    assert applied['template_id'] == 'ecommerce_assistant' and applied['objectives'] != agent['objectives']
    assert not applied['appointments_enabled']
    cleared = authenticated_client.patch(url, json={'template_id': None}).json()
    assert cleared['template_version'] is None and cleared['template_snapshot'] is None
    assert cleared['instructions'] == applied['instructions']


def test_ready_calendar_recommends_existing_permission_bundle(authenticated_client):
    client = authenticated_client
    item = business(client)
    result = client.post('/api/appointment-services', json={'client_id': item['id'], 'name': 'Consultation', 'duration_minutes': 30})
    assert result.status_code == 201, result.text
    result = client.put('/api/availability', json={'client_id': item['id'], 'timezone': 'UTC', 'rules': [{'weekday': 1, 'start_time': '09:00', 'end_time': '17:00'}]})
    assert result.status_code == 200, result.text
    data = preview(client, item)
    assert 'create_appointment' in data['defaults']['selected_tools']
    assert not data['unavailable_tools']
    response = client.post('/api/agents', json={**data['defaults'], 'client_id': item['id'], 'apply_template': True})
    assert response.status_code == 201, response.text
    assert response.json()['appointments_enabled']
    assert not data['google_connected']  # Native calendar works without OAuth.


def test_template_workspace_isolation(authenticated_client):
    with TestingSession() as db:
        agency = Agency(name='Other workspace', slug='other-templates')
        db.add(agency); db.flush()
        foreign = Client(agency_id=agency.id, name='Private', portal_slug='private-templates')
        db.add(foreign); db.commit(); foreign_id = str(foreign.id)
    root = f'/api/catalog/agent-templates/{foreign_id}'
    assert authenticated_client.post(root + '/recommendations', json={}).status_code == 404
    assert authenticated_client.get(root + '/veterinary_receptionist/preview').status_code == 404
    assert authenticated_client.post('/api/agents', json={'client_id': foreign_id, 'name': 'No', 'template_id': 'veterinary_receptionist', 'apply_template': True}).status_code == 400


def test_retired_references_are_omitted_with_warnings():
    data, warnings = validated_definition(replace(TEMPLATES[0], recommended_tools=('knowledge', 'retired'), suggested_automations=('confirmation', 'retired'), objectives=('sales', 'retired'), recommended_channels=('widget', 'amazon')))
    assert data['recommended_tools'] == ['knowledge']
    assert data['suggested_automations'] == ['confirmation']
    assert data['objectives'] == ['sales'] and data['recommended_channels'] == ['widget']
    assert len(warnings) == 4


def test_calendar_readiness_is_not_shared_between_businesses(authenticated_client):
    client = authenticated_client
    ready = business(client)
    other = business(client, name='Another veterinary')
    assert client.post('/api/appointment-services', json={'client_id': ready['id'], 'name': 'Consultation', 'duration_minutes': 30}).status_code == 201
    assert client.put('/api/availability', json={'client_id': ready['id'], 'timezone': 'UTC', 'rules': [{'weekday': 1, 'start_time': '09:00', 'end_time': '17:00'}]}).status_code == 200
    assert 'create_appointment' in preview(client, ready)['defaults']['selected_tools']
    assert 'create_appointment' not in preview(client, other)['defaults']['selected_tools']


def test_automation_suggestions_only_create_after_explicit_consent(authenticated_client):
    client = authenticated_client
    item = business(client)
    data = preview(client, item)
    assert client.post('/api/agents', json={**data['defaults'], 'client_id': item['id'], 'apply_template': True}).status_code == 201
    assert client.get('/api/automations').json() == []
    response = client.post('/api/automations', json={'name': 'Appointment confirmation', 'client_id': item['id'], 'template_id': 'confirmation', 'enabled': True, 'trigger_type': 'appointment_created', 'actions': [{'type': 'send_message', 'text': 'Your appointment is confirmed.'}]})
    assert response.status_code == 201, response.text
    assert client.get('/api/automations').json()[0]['template_id'] == 'confirmation'
    preview(client, item)
    assert len(client.get('/api/automations').json()) == 1
