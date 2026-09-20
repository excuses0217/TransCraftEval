import json
from threading import Lock

import pytest
from fastapi.testclient import TestClient

from face_watch.api import create_app


def activate_person(c: TestClient, item_id: str = 'person.jackie_chan') -> dict:
    submitted = c.post(f'/api/library-items/{item_id}/lifecycle', json={'action':'submit_for_validation'})
    assert submitted.status_code == 200
    validated = c.post(f'/api/library-items/{item_id}/validation', json={'decision':'passed', 'note':'独立媒资盲测通过，允许进入生产对象库。'})
    assert validated.status_code == 200
    activated = c.post(f'/api/library-items/{item_id}/lifecycle', json={'action':'activate'})
    assert activated.status_code == 200
    return activated.json()


def test_saved_library_is_authoritative(tmp_path):
    state=tmp_path/'state.json'
    c=TestClient(create_app(state_file=state))
    item=c.get('/api/library-items').json()[2]
    assert c.post('/api/library-items/'+item['item_id']+'/lifecycle',json={'action':'disable','note':'测试停用'}).status_code==200
    item=c.get('/api/library-items').json()[2]
    item.update(definition='人工维护内容')
    assert c.put('/api/library-items/'+item['item_id'],json=item).status_code==200
    before=c.get('/api/library-items').json()
    restarted=TestClient(create_app(state_file=state))
    assert restarted.get('/api/library-items').json()==before


def test_corrupt_state_is_not_overwritten(tmp_path):
    state=tmp_path/'state.json'
    state.write_text('invalid')
    with pytest.raises(RuntimeError):
        create_app(state_file=state)
    assert state.read_text()=='invalid'


def test_production_gate_and_capability_contract(tmp_path):
    video=tmp_path/'local.mp4'
    video.touch()
    c=TestClient(create_app())
    request={'name':'核查','asset_path':str(video),'object_ids':['person.jackie_chan'],'purpose':'production'}
    assert c.post('/api/review-tasks',json=request).status_code==422
    item=next(item for item in c.get('/api/library-items').json() if item['item_id']=='person.jackie_chan')
    item['status']='active'
    assert c.put('/api/library-items/'+item['item_id'],json=item).status_code==409
    assert activate_person(c, item['item_id'])['status']=='active'
    assert c.post('/api/review-tasks',json=request).status_code==201
    assert c.post('/api/review-tasks',json={**request,'capabilities':['face','ocr']}).status_code==422
    assert c.post('/api/review-tasks',json={**request,'object_ids':['text.seed_terms']}).status_code==422
    other=tmp_path/'ordinary.txt'
    other.touch()
    assert c.post('/api/review-tasks',json={**request,'asset_path':str(other)}).status_code==422


def test_scope_edit_and_state_guard(tmp_path):
    video=tmp_path/'local.mp4'
    video.touch()
    c=TestClient(create_app())
    request={'name':'验证','asset_path':str(video),'object_ids':['person.zhao_benshan']}
    task=c.post('/api/review-tasks',json=request).json()
    url='/api/review-tasks/'+task['task_id']
    assert c.put(url+'/scope',json={**request,'name':'修改后'}).json()['name']=='修改后'
    assert c.patch(url,json={'status':'needs_review'}).status_code==409
    assert c.put(url+'/scope',json={**request,'purpose':'production'}).status_code==422


def test_retry_preserves_previous_result(tmp_path):
    video=tmp_path/'local.mp4'
    video.touch()
    state=tmp_path/'state.json'
    c=TestClient(create_app(state_file=state))
    task=c.post('/api/review-tasks',json={'name':'旧任务','asset_path':str(video),'object_ids':['person.zhao_benshan']}).json()
    assert task['created_at']
    saved=json.loads(state.read_text())
    saved['review_tasks'][0].update(status='needs_review',result={'events':[],'metrics':{'coverage_complete':False}})
    state.write_text(json.dumps(saved))
    c=TestClient(create_app(state_file=state))
    url='/api/review-tasks/'+task['task_id']
    assert c.post(url+'/complete').status_code==409
    new=c.post(url+'/retry')
    assert new.status_code==201
    assert new.json()['previous_task_id']==task['task_id']
    assert new.json()['status']=='ready'
    assert 'result' not in new.json()
    assert c.get(url).json()['result']['metrics']['coverage_complete'] is False


def test_execution_rechecks_production_gate(tmp_path):
    video=tmp_path/'local.mp4'
    video.touch()
    class Stub:
        _analysis_lock=Lock()
    c=TestClient(create_app(analyzer=Stub(),artifact_dir=tmp_path/'artifacts'))
    item=activate_person(c)
    task=c.post('/api/review-tasks',json={'name':'生产','asset_path':str(video),'object_ids':[item['item_id']],'purpose':'production'}).json()
    c.post('/api/library-items/'+item['item_id']+'/lifecycle',json={'action':'disable','note':'验证生产门禁'})
    assert c.post('/api/review-tasks/'+task['task_id']+'/run').status_code==422


def test_completed_review_requires_explicit_reopen_and_keeps_a_version(tmp_path):
    video=tmp_path/'local.mp4'
    video.touch()
    state=tmp_path/'state.json'
    c=TestClient(create_app(state_file=state))
    task=c.post('/api/review-tasks',json={'name':'可追溯审核','asset_path':str(video),'object_ids':['person.zhao_benshan']}).json()
    saved=json.loads(state.read_text())
    saved['review_tasks'][0].update(status='needs_review',result={'events':[{'event_id':'event-1','person_id':'person.zhao_benshan','person_name':'赵本山','start_seconds':10,'review_status':'confirmed'}],'metrics':{'coverage_complete':True}})
    state.write_text(json.dumps(saved))
    c=TestClient(create_app(state_file=state))
    url='/api/review-tasks/'+task['task_id']
    completed=c.post(url+'/complete')
    assert completed.status_code==200
    assert completed.json()['audit_versions'][0]['version']==1
    assert c.patch(url+'/events/event-1',json={'review_status':'rejected','reason':'not_target'}).status_code==409
    reopened=c.post(url+'/reopen',json={'reason':'new_evidence','note':'补充了更清晰的上下文片段。'})
    assert reopened.status_code==200
    assert reopened.json()['status']=='needs_review'
    assert reopened.json()['audit_versions'][0]['events'][0]['review_status']=='confirmed'
    assert c.patch(url+'/events/event-1',json={'review_status':'rejected','reason':'not_target'}).status_code==200


def test_result_covers_every_object_in_the_original_scope(tmp_path):
    video = tmp_path / 'local.mp4'
    video.touch()
    state = tmp_path / 'state.json'
    client = TestClient(create_app(state_file=state))
    task = client.post('/api/review-tasks', json={
        'name': '全对象审核结论',
        'asset_path': str(video),
        'object_ids': ['person.zhao_benshan', 'person.zhu_shimao'],
    }).json()
    saved = json.loads(state.read_text())
    saved['review_tasks'][0].update(
        analysis_profile='track_v3_continuity',
        status='needs_review',
        result={
            'events': [{
                'event_id': 'event-1',
                'person_id': 'person.zhao_benshan',
                'person_name': '赵本山',
                'start_seconds': 10,
                'review_status': 'confirmed',
            }],
            'metrics': {'coverage_complete': True},
        },
    )
    state.write_text(json.dumps(saved))
    client = TestClient(create_app(state_file=state))

    result = client.get(f"/api/review-tasks/{task['task_id']}").json()['result']

    assert [summary['name'] for summary in result['object_summaries']] == ['赵本山', '朱时茂']
    assert [summary['conclusion'] for summary in result['object_summaries']] == ['confirmed', 'not_found']
    report = client.get(f"/api/review-tasks/{task['task_id']}/report")
    assert '系统未发现' in report.text
    assert '证据指数' in report.text


def test_zero_candidate_complete_creates_a_versioned_no_findings_result(tmp_path):
    video = tmp_path / 'local.mp4'
    video.touch()
    state = tmp_path / 'state.json'
    client = TestClient(create_app(state_file=state))
    task = client.post('/api/review-tasks', json={
        'name': '零命中审核',
        'asset_path': str(video),
        'object_ids': ['person.zhao_benshan'],
    }).json()
    saved = json.loads(state.read_text())
    saved['review_tasks'][0].update(
        analysis_profile='track_v3_continuity',
        status='needs_review',
        result={'events': [], 'metrics': {'coverage_complete': True}},
    )
    state.write_text(json.dumps(saved))
    client = TestClient(create_app(state_file=state))

    completed = client.get(f"/api/review-tasks/{task['task_id']}")

    assert completed.status_code == 200
    assert completed.json()['status'] == 'completed'
    assert completed.json()['audit_version'] == 1
    assert completed.json()['result']['object_summaries'][0]['conclusion'] == 'not_found'


def test_overview_is_scoped_by_workspace_purpose(tmp_path):
    video=tmp_path/'local.mp4'
    video.touch()
    c=TestClient(create_app())
    validation=c.post('/api/review-tasks',json={'name':'验证任务','asset_path':str(video),'object_ids':['person.zhao_benshan']})
    assert validation.status_code==201
    active=activate_person(c)
    production=c.post('/api/review-tasks',json={'name':'生产任务','asset_path':str(video),'object_ids':[active['item_id']],'purpose':'production'})
    assert production.status_code==201
    assert [task['name'] for task in c.get('/api/overview?purpose=validation').json()['tasks']]==['验证任务']
    assert [task['name'] for task in c.get('/api/overview?purpose=production').json()['tasks']]==['生产任务']
