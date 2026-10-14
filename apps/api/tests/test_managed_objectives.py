"""Managed objectives use the production queue and tools on disposable data."""
import asyncio
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock
from sqlalchemy import select
from conftest import TestingSession, customer_conversation
from app.models import Agency, Agent, AgentQA, Automation, AutomationRun, Client, Conversation, Message, ScheduledAutomationAction, now_utc
from app.services.automations import worker
from app.services.tools.runner import run_completion
from app.services.tools.knowledge import build_knowledge_spec
from app.services.tools.leads import build_lead_spec
from test_appointments import setup, slots, booking


def create(client, objectives, config=None, cid=None):
    if not cid:
        cid = client.post('/api/clients', json={'name': 'Objective business'}).json()['id']
    response = client.post('/api/agents', json={'client_id': cid, 'name': 'Managed', 'objectives': objectives, 'objective_config': config or {}, 'model': 'gpt-4.1-mini'})
    assert response.status_code == 201, response.text
    return response.json()


def rows(agent_id):
    with TestingSession() as db:
        return [(str(row.id), row.objective_id, row.rule_key, row.enabled, row.trigger_config) for row in db.scalars(select(Automation).where(Automation.agent_id == uuid.UUID(agent_id)))]


def force_due():
    with TestingSession() as db:
        for job in db.scalars(select(ScheduledAutomationAction).where(ScheduledAutomationAction.status == 'pending')):
            job.execute_at = now_utc() - timedelta(seconds=1)
        db.commit()
    with TestingSession() as db:
        asyncio.run(worker.process_due(db))


def test_managed_creation_update_disable_and_custom_rules_untouched(authenticated_client):
    client = authenticated_client
    agent = create(client, ['follow_up'], {'follow_up': {'first_minutes': 2, 'second_minutes': 5}})
    url = '/api/agents/' + agent['id']
    initial = rows(agent['id'])
    assert len(initial) == 1 and initial[0][-1] == {'minutes': 2}
    assert client.get(url).json()['objective_config']['follow_up']['second_minutes'] == 5
    custom = client.post('/api/automations', json={'name': 'Custom untouched', 'client_id': agent['client_id'], 'trigger_type': 'message_received', 'actions': [{'type': 'handoff_to_human'}]}).json()
    assert client.patch(url, json={'objective_config': {'follow_up': {'first_minutes': 240}}}).status_code == 200
    assert rows(agent['id'])[0][0] == initial[0][0] and rows(agent['id'])[0][-1] == {'minutes': 240}
    assert client.patch(url, json={'objectives': []}).status_code == 200
    assert not rows(agent['id'])[0][3]
    assert client.get('/api/automations/' + custom['id']).json()['enabled']
    assert client.patch(url, json={'objectives': ['follow_up']}).status_code == 200
    assert rows(agent['id'])[0][0] == initial[0][0] and rows(agent['id'])[0][3]
    assert client.patch('/api/automations/' + initial[0][0], json={'enabled': False}).status_code == 409
    assert len(client.get('/api/automations').json()) == 1


def test_followup_starts_from_first_reply_two_attempts_and_new_activity_cancels(authenticated_client):
    client = authenticated_client
    agent = create(client, ['follow_up'], {'follow_up': {'first_minutes': 2, 'second_minutes': 5, 'message': 'Can we help you continue?'}})
    conv = customer_conversation(client, agent['id'])
    with TestingSession() as db:
        db.add(Message(conversation_id=uuid.UUID(conv['id']), role='user', content='How much?')); db.commit()
    with TestingSession() as db:
        assert not db.scalar(select(AutomationRun.id))
        db.add(Message(conversation_id=uuid.UUID(conv['id']), role='assistant', content='Here is our pricing.')); db.commit()
    with TestingSession() as db:
        job = db.scalar(select(ScheduledAutomationAction))
        assert job.execute_at > now_utc() + timedelta(seconds=90)
    force_due()
    with TestingSession() as db:
        messages = db.scalars(select(Message).where(Message.sender_type == 'automation')).all()
        assert len(messages) == 1 and messages[0].content == 'Can we help you continue?'
        pending = db.scalar(select(ScheduledAutomationAction).where(ScheduledAutomationAction.status == 'pending'))
        assert pending.execute_at > now_utc() + timedelta(minutes=4)
    force_due()
    with TestingSession() as db:
        assert len(db.scalars(select(Message).where(Message.sender_type == 'automation')).all()) == 2
        assert not db.scalar(select(ScheduledAutomationAction.id).where(ScheduledAutomationAction.status == 'pending'))
        db.add(Message(conversation_id=uuid.UUID(conv['id']), role='assistant', content='Another response')); db.commit()
    force_due()  # First new attempt.
    with TestingSession() as db:
        db.add(Message(conversation_id=uuid.UUID(conv['id']), role='user', content='I am here')); db.commit()
    force_due()
    with TestingSession() as db:
        assert len(db.scalars(select(Message).where(Message.sender_type == 'automation')).all()) == 3


def test_rules_are_agent_scoped_even_inside_same_business(authenticated_client):
    client = authenticated_client
    first = create(client, ['follow_up'])
    other = create(client, ['respond_questions'], cid=first['client_id'])
    conv = customer_conversation(client, other['id'])
    with TestingSession() as db:
        db.add(Message(conversation_id=uuid.UUID(conv['id']), role='assistant', content='Other agent')); db.commit()
    with TestingSession() as db:
        assert not db.scalar(select(AutomationRun.id))


def test_real_booking_confirmation_reminders_and_postservice(authenticated_client):
    client = authenticated_client
    cid, sid, day = setup(client)
    agent = create(client, ['book_appointment', 'appointment_reminder', 'post_appointment_followup'], cid=cid)
    assert agent['appointments_enabled']
    assert len(rows(agent['id'])) == 4
    conv = customer_conversation(client, agent['id'])
    start = slots(client, cid, sid, day)['slots'][0]['starts_at']
    payload = booking(cid, sid, start, agent_id=agent['id'], conversation_id=conv['id'])
    response = client.post('/api/appointments', json=payload)
    assert response.status_code == 201, response.text
    force_due()
    with TestingSession() as db:
        assert db.scalar(select(Message.id).where(Message.sender_type == 'automation'))
        assert db.scalar(select(AutomationRun.id).where(AutomationRun.event_type == 'appointment_upcoming'))
    assert client.post('/api/appointments/' + response.json()['id'] + '/complete').status_code == 200
    force_due()
    with TestingSession() as db:
        assert db.scalar(select(AutomationRun.id).where(AutomationRun.event_type == 'appointment_completed', AutomationRun.status == 'success'))


def test_handoff_and_knowledge_are_real_without_model_guessing(authenticated_client, monkeypatch):
    client = authenticated_client
    agent = create(client, ['handoff_to_human', 'respond_questions'])
    conv = customer_conversation(client, agent['id'])
    with TestingSession() as db:
        model = db.get(Agent, uuid.UUID(agent['id']))
        current = db.get(Conversation, uuid.UUID(conv['id']))
        result = asyncio.run(run_completion(db, model, 'https://example.test', 'fixture', [{'role': 'user', 'content': 'quiero hablar con una persona'}], conversation=current))
        db.commit()
        assert result.tool_calls and db.get(Conversation, current.id).mode == 'human'
        db.add(AgentQA(agent_id=model.id, question='Hours?', answer='9 to 18')); db.commit()
        spec = build_knowledge_spec(model)
        text, failed = asyncio.run(spec.handler({'query': 'Hours'}))
        assert not failed and '9 to 18' in text
    assert client.get('/api/conversations').json()[0]['mode'] == 'human'


def test_lead_classification_and_selected_fields(authenticated_client):
    agent = create(authenticated_client, ['lead_qualification'], {'lead_qualification': {'fields': ['need', 'budget', 'date']}})
    conv = customer_conversation(authenticated_client, agent['id'])
    with TestingSession() as db:
        current = db.get(Agent, uuid.UUID(agent['id']))
        conversation = db.get(Conversation, uuid.UUID(conv['id']))
        spec = build_lead_spec(current, conversation)
        text, failed = asyncio.run(spec.handler({'need': 'Consulting', 'budget': '500', 'date': 'Next week'}))
        assert not failed and 'hot' in text
        _, failed = asyncio.run(spec.handler({'phone': '555'}))
        assert failed
    with TestingSession() as db:
        assert db.get(Conversation, uuid.UUID(conv['id'])).lead_temperature == 'hot'


def test_unavailable_calendar_commerce_and_tenant_service_selection(authenticated_client):
    client = authenticated_client
    agent = create(client, ['book_appointment'])
    assert not agent['appointments_enabled'] and agent['objective_status']['book_appointment']['state'] == 'needs_configuration'
    result = client.post('/api/agents', json={'name': 'Unsupported', 'client_id': agent['client_id'], 'objectives': ['order_lookup']})
    assert result.status_code == 422
    cid, sid, _ = setup(client)
    assert client.patch('/api/agents/' + agent['id'], json={'objective_config': {'book_appointment': {'service_ids': [sid]}}}).status_code == 422
    with TestingSession() as db:
        other = Agency(name='Other', slug='other-managed'); db.add(other); db.flush()
        foreign = Client(agency_id=other.id, name='Foreign', portal_slug='foreign-managed'); db.add(foreign); db.commit(); foreign_id = str(foreign.id)
    assert client.post('/api/catalog/objective-configuration/' + foreign_id, json={'objectives': ['follow_up']}).status_code == 404
    assert client.patch('/api/agents/' + agent['id'], json={'objective_config': {'invented': {}}}).status_code == 422


def test_revoked_permission_survives_unrelated_edits_and_legacy_is_not_adopted(authenticated_client):
    client = authenticated_client
    agent = create(client, ['respond_questions'])
    url = '/api/agents/' + agent['id']
    assert client.patch(url, json={'selected_tools': []}).status_code == 200
    edited = client.patch(url, json={'name': 'Still revoked'}).json()
    assert not edited['knowledge_enabled'] and edited['selected_tools'] == []
    legacy = client.post('/api/agents', json={'name': 'Legacy', 'client_id': agent['client_id']}).json()
    assert not legacy['objectives_managed']
    edited = client.patch('/api/agents/' + legacy['id'], json={'name': 'Preserved'}).json()
    assert not edited['objectives_managed'] and not rows(legacy['id'])


def test_template_apply_creates_managed_rules_with_pinned_configuration(authenticated_client):
    client = authenticated_client
    cid = client.post('/api/clients', json={'name': 'Veterinary', 'industry': 'health_wellness', 'business_type': 'veterinary'}).json()['id']
    response = client.post('/api/agents', json={'client_id': cid, 'name': 'Reception', 'template_id': 'veterinary_receptionist', 'apply_template': True})
    assert response.status_code == 201, response.text
    agent = response.json()
    assert agent['template_version'] == 1 and agent['objectives_managed']
    assert {'follow_up', 'appointment_reminder'} <= set(agent['objectives'])
    assert len(rows(agent['id'])) == 4
    assert client.get('/api/agents/' + agent['id']).json()['objective_config'] == agent['objective_config']
    assert client.get('/api/automations').json() == []
