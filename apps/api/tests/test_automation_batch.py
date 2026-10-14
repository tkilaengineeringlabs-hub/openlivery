"""Multi-select saves use existing records, worker and tenant boundaries."""
import uuid
from copy import deepcopy
from conftest import TestingSession, customer_conversation
from app.models import Agency, Client, Conversation
from app.services.automations.worker import process_due
import asyncio


def batch(client):
    business = client.post('/api/clients', json={'name': 'Batch veterinary', 'industry': 'health_wellness', 'business_type': 'veterinary'}).json()
    agent = client.post('/api/agents', json={'client_id': business['id'], 'name': 'Receptionist', 'objectives': ['customer_support', 'book_appointment', 'follow_up', 'handoff_to_human']}).json()
    items = []
    for code, trigger, minutes in [('confirmation', 'appointment_created', None), ('reminder24', 'appointment_upcoming', 1440), ('reminder2', 'appointment_upcoming', 120), ('followUp', 'conversation_inactive', 30), ('handoff', 'message_received', None)]:
        action = {'id': str(uuid.uuid4()), 'type': 'handoff_to_human'} if code == 'handoff' else {'id': str(uuid.uuid4()), 'type': 'send_message', 'text': 'Fixture message'}
        items.append({'id': str(uuid.uuid4()), 'configuration': {'name': code, 'client_id': business['id'], 'template_id': code, 'trigger_type': trigger, 'trigger_config': {'minutes': minutes} if minutes else {}, 'conditions': [{'field': 'message.text', 'operator': 'contains', 'value': 'human'}] if code == 'handoff' else [], 'actions': [action]}})
    return business, agent, {'items': items}


def test_batch_creates_five_records_retries_edits_and_pauses_independently(authenticated_client):
    client = authenticated_client
    business, agent, payload = batch(client)
    response = client.post('/api/automations/batch', json=payload)
    assert response.status_code == 201, response.text
    records = response.json()
    assert len(records) == 5 and all(r['client_id'] == business['id'] for r in records)
    assert client.post('/api/automations/batch', json=payload).status_code == 201
    assert len(client.get('/api/automations').json()) == 5
    first = records[0]['id']
    assert client.patch(f'/api/automations/{first}', json={'name': 'Edited confirmation'}).status_code == 200
    assert client.post(f'/api/automations/{first}/disable').json()['enabled'] is False
    assert sum(item['enabled'] for item in client.get('/api/automations').json()) == 4
    assert client.post('/api/automations/batch', json=payload).status_code == 409
    conversation = customer_conversation(client, agent['id'])
    # Batch-created handoff runs in the existing worker, not a new engine.
    from app.models import Message
    with TestingSession() as db:
        db.add(Message(conversation_id=uuid.UUID(conversation['id']), role='user', content='human please'))
        db.commit()
    with TestingSession() as db:
        asyncio.run(process_due(db))
    with TestingSession() as db:
        assert db.get(Conversation, uuid.UUID(conversation['id'])).mode == 'human'


def test_batch_rollback_and_cross_workspace_isolation(authenticated_client):
    client = authenticated_client
    business, _, payload = batch(client)
    with TestingSession() as db:
        agency = Agency(name='Other', slug='other-batch')
        db.add(agency); db.flush()
        foreign = Client(agency_id=agency.id, name='Foreign', portal_slug='foreign-batch')
        db.add(foreign); db.commit(); foreign_id = str(foreign.id)
    invalid = deepcopy(payload)
    for item in invalid['items']:
        item['configuration']['client_id'] = foreign_id
    assert client.post('/api/automations/batch', json=invalid).status_code == 404
    assert client.get('/api/automations').json() == []
    invalid = deepcopy(payload)
    invalid['items'][-1]['configuration']['actions'] = [{'type': 'http_request', 'url': 'http://127.0.0.1/private'}]
    assert client.post('/api/automations/batch', json=invalid).status_code == 422
    assert client.get('/api/automations').json() == []
    assert client.get('/api/automations/recommendations', params={'client_id': foreign_id}).status_code == 404
    invalid = deepcopy(payload)
    invalid['items'][0]['configuration']['template_id'] = 'newLead'
    assert client.post('/api/automations/batch', json=invalid).status_code == 422
    invalid = deepcopy(payload)
    invalid['items'][0]['configuration']['client_id'] = foreign_id
    assert client.post('/api/automations/batch', json=invalid).status_code == 422


def test_recommendations_reuse_industry_and_agent_objectives(authenticated_client):
    business, _, _ = batch(authenticated_client)
    result = authenticated_client.get('/api/automations/recommendations', params={'client_id': business['id']})
    assert result.status_code == 200
    assert {'confirmation', 'reminder24', 'reminder2', 'afterAppointment', 'handoff'} <= set(result.json()['ids'])
    assert authenticated_client.get('/api/automations').json() == []


def test_http_batch_retry_preserves_encrypted_headers(authenticated_client, monkeypatch):
    from app.routers import automations as router
    from app.models import Automation
    client = authenticated_client
    business, _, _ = batch(client)
    monkeypatch.setattr(router, '_blocked_reason', lambda *args, **kwargs: None)
    payload = {'items': [{'id': str(uuid.uuid4()), 'configuration': {'name': 'HTTP fixture', 'client_id': business['id'], 'template_id': 'webhook', 'trigger_type': 'message_received', 'actions': [{'id': str(uuid.uuid4()), 'type': 'http_request', 'url': 'https://example.com/hook', 'headers': {'Authorization': 'synthetic-fixture-token'}}]}}]}
    response = client.post('/api/automations/batch', json=payload)
    assert response.status_code == 201, response.text
    assert 'synthetic-fixture-token' not in response.text
    assert client.post('/api/automations/batch', json=payload).status_code == 201
    with TestingSession() as db:
        stored = db.get(Automation, uuid.UUID(payload['items'][0]['id']))
        assert 'synthetic-fixture-token' not in str(stored.actions)
    changed = deepcopy(payload)
    changed['items'][0]['configuration']['actions'][0]['headers']['Authorization'] = 'different-fixture-token'
    assert client.post('/api/automations/batch', json=changed).status_code == 409
    assert len(client.get('/api/automations').json()) == 1
