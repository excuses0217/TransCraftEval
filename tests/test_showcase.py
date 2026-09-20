import json
import os
import subprocess
import time
from threading import Lock
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from face_watch.api import create_app
from face_watch.showcase import load_bundle


def fixture_bundle(root):
    root.mkdir()
    (root/'clip.mp4').write_bytes(b'video')
    (root/'ref.jpg').write_bytes(b'image')
    item = {'item_id':'person.test', 'category':'person', 'name':'测试人物', 'classification':'演员',
            'definition':'测试', 'aliases':[], 'status':'ready_for_validation',
            'materials':[{'material_id':'ref', 'kind':'reference_image', 'title':'照片', 'local_uri':'/bundled/ref.jpg', 'quality_note':'待验证','status':'pending_validation'}]}
    (root/'seed.json').write_text(json.dumps({'library_items':[item], 'review_tasks':[{'task_id':'seed', 'name':'片段', 'asset_path':'clip.mp4','object_ids':['person.test'], 'status':'ready','purpose':'validation','capabilities':['face']}]}))
    (root/'catalog.json').write_text(json.dumps([{'name':'片段','path':'clip.mp4','url':'/bundled/clip.mp4'}]))


def test_bundle_portable_and_persistent(tmp_path):
    bundle=tmp_path/'bundle'
    fixture_bundle(bundle)
    seed,catalog=load_bundle(bundle)
    state=tmp_path/'runtime/state.json'
    c=TestClient(create_app(seed_state=seed,media_catalog=catalog,bundled_dir=bundle,state_file=state))
    library = c.get('/api/library-items').json()
    assert {key: library[0][key] for key in seed['library_items'][0]} == seed['library_items'][0]
    assert library[0]['validation']['status'] == 'not_started'
    assert library[0]['lifecycle_history'] == []
    assert c.get('/api/local-media').json()[0]['path']==str(bundle/'clip.mp4')
    assert c.get('/bundled/clip.mp4',headers={'Range':'bytes=0-1'}).status_code==206
    item=c.get('/api/library-items').json()[0]
    item['definition']='用户修改应保留'
    assert c.put('/api/library-items/person.test',json=item).status_code==200
    restarted=TestClient(create_app(seed_state=seed,state_file=state))
    assert restarted.get('/api/library-items').json()[0]['definition']=='用户修改应保留'
    assert len(restarted.get('/api/review-tasks').json())==1
    assert json.loads((bundle/'seed.json').read_text())['library_items'][0]['definition']=='测试'


def test_bundle_rejects_missing_and_outside_files(tmp_path):
    bundle=tmp_path/'bundle'
    fixture_bundle(bundle)
    data=json.loads((bundle/'catalog.json').read_text())
    for path in ('missing.mp4','../outside.mp4'):
        data[0]['path']=path
        (bundle/'catalog.json').write_text(json.dumps(data))
        with pytest.raises(ValueError):
            load_bundle(bundle)


def test_showcase_launcher_check():
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run(['sh',str(root/'scripts/start_showcase.sh')],env={**os.environ,'FACE_WATCH_CHECK_ONLY':'1'},capture_output=True,text=True,check=True)
    assert 'profile=showcase port=8770' in result.stdout
    assert 'data/showcase/state.json' in result.stdout


def test_task_uses_bundled_references(tmp_path, monkeypatch):
    bundle=tmp_path/'bundle'
    fixture_bundle(bundle)
    seed,catalog=load_bundle(bundle)
    received=[]
    def run(analyzer, video, people, output, progress, interval, policy):
        received.append(people[0]['paths'])
        assert video==bundle/'clip.mp4'
        return {'events':[], 'metrics':{'coverage_complete':True}, 'reference_snapshot':[]}
    monkeypatch.setattr('face_watch.video_track_runner.run_track_review',run)
    class Analyzer:
        _analysis_lock=Lock()
    client=TestClient(create_app(analyzer=Analyzer(), seed_state=seed, media_catalog=catalog,
        bundled_dir=bundle, artifact_dir=tmp_path/'artifacts', state_file=tmp_path/'runtime.json'))
    assert client.post('/api/review-tasks/seed/run').status_code==202
    for _ in range(100):
        task=client.get('/api/review-tasks/seed').json()
        if task['status']!='running':
            break
        time.sleep(.01)
    assert task['status']=='completed'
    assert task['candidate_count']==0
    assert task['audit_versions'][0]['events']==[]
    assert received==[[bundle/'ref.jpg']]
