from pathlib import Path
import json
from fastapi.testclient import TestClient
from face_watch.api import create_app


def test_review_survives_restart_and_retains_history(tmp_path):
    state = tmp_path/'state.json'
    state.write_text(json.dumps({'library_items':[], 'review_tasks':[{'task_id':'t', 'name':'test', 'asset_path':str(tmp_path/'video.mp4'), 'object_ids':[], 'analysis_profile':'track_v3_continuity', 'status':'needs_review', 'result':{'events':[{'event_id':'e', 'review_status':'pending', 'start_seconds':0,'person_name':'test'}]}}]}))
    client = TestClient(create_app(state_file=state))
    response = client.patch('/api/review-tasks/t/events/e', json={'review_status':'rejected', 'note':'不是目标'})
    assert response.status_code == 200
    assert response.json()['status'] == 'needs_review'
    assert response.json()['result']['events'][0]['confidence_is_probability'] is False
    assert client.post('/api/review-tasks/t/complete').json()['status'] == 'completed'
    assert client.get('/api/review-tasks/t/report').status_code == 200
    restarted = TestClient(create_app(state_file=state))
    event = restarted.get('/api/review-tasks/t').json()['result']['events'][0]
    assert event['note'] == '不是目标'
    assert event['confidence_is_probability'] is False
    assert 0 <= event['confidence_score'] <= 100
    assert event['history'][0]['previous'] == 'pending'
    assert restarted.patch('/api/review-tasks/t/events/e', json={'review_status':'uncertain'}).status_code == 409
    assert restarted.post('/api/review-tasks/t/reopen', json={'reason':'correction','note':'需要更正已保存的人工判断。'}).status_code == 200
    response = restarted.patch('/api/review-tasks/t/events/e', json={'review_status':'uncertain'})
    assert response.json()['status'] == 'needs_review'
    assert len(response.json()['result']['events'][0]['history']) == 2
    assert restarted.patch('/api/review-tasks/t', json={'status':'completed'}).status_code == 409


def test_restart_marks_running_task_interrupted(tmp_path):
    state = tmp_path/'state.json'
    state.write_text(json.dumps({'library_items':[], 'review_tasks':[{'task_id':'t','status':'running'}]}))
    client = TestClient(create_app(state_file=state))
    assert client.get('/api/review-tasks/t').json()['status'] == 'failed'
    assert client.get('/api/review-tasks/missing').status_code == 404


def test_review_task_can_be_renamed_after_analysis(tmp_path):
    state = tmp_path / 'state.json'
    state.write_text(json.dumps({
        'library_items': [],
        'review_tasks': [{
            'task_id': 't',
            'name': '技术过程名称',
            'status': 'needs_review',
            'analysis_profile': 'track_v3_continuity',
            'result': {'events': []},
        }],
    }))
    client = TestClient(create_app(state_file=state))

    response = client.patch('/api/review-tasks/t/name', json={'name': '牧马人 · 片段 1 · 人物审核'})

    assert response.status_code == 200
    assert response.json()['name'] == '牧马人 · 片段 1 · 人物审核'
    restarted = TestClient(create_app(state_file=state))
    assert restarted.get('/api/review-tasks/t').json()['name'] == '牧马人 · 片段 1 · 人物审核'


def test_existing_task_can_be_consolidated_without_losing_reviews(tmp_path):
    state = tmp_path/'state.json'
    events = [
        {'event_id':'a','person_id':'p','person_name':'演员','start_seconds':1,'end_seconds':1,'review_status':'confirmed','reason':'appearance'},
        {'event_id':'b','person_id':'p','person_name':'演员','start_seconds':5,'end_seconds':5,'review_status':'confirmed','reason':'appearance'},
    ]
    state.write_text(json.dumps({'library_items':[], 'review_tasks':[{'task_id':'t','status':'needs_review','result':{'events':events}}]}))
    client = TestClient(create_app(state_file=state))
    response = client.post('/api/review-tasks/t/consolidate-events', json={'gap_seconds':4})
    assert response.status_code == 200
    task = response.json()
    assert task['candidate_count'] == 1
    assert task['result']['events'][0]['review_status'] == 'confirmed'
    assert task['result']['events'][0]['segment_count'] == 2
    assert task['audit_history'][-1]['event'] == 'events_consolidated'
