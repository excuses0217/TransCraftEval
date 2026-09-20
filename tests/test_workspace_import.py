import json
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from face_watch.api import create_app
from face_watch.showcase import load_bundle


def workspace(tmp_path, bundle=None):
    return TestClient(create_app(seed_state={'library_items':[], 'review_tasks':[]},
        state_file=tmp_path/'state.json', artifact_dir=tmp_path/'artifacts',
        media_catalog=[], bundled_dir=bundle, setup_enabled=True))


def video_bytes(tmp_path):
    path=tmp_path/'source.mp4'
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),5,(64,64))
    assert writer.isOpened()
    for _ in range(5):
        writer.write(np.zeros((64,64,3),dtype=np.uint8))
    writer.release()
    return path.read_bytes()


def test_empty_setup_skip_and_restart(tmp_path):
    c=workspace(tmp_path)
    assert c.get('/api/workspace/setup').json()=={'enabled':True,'initialized':False,'bundle_available':False,'media_count':0}
    assert c.get('/api/library-items').json()==[]
    assert c.get('/api/local-media').json()==[]
    assert c.post('/api/workspace/import-defaults').status_code==404
    assert c.post('/api/workspace/skip').status_code==200
    assert workspace(tmp_path).get('/api/workspace/setup').json()['initialized'] is True


def test_local_import_persists_deduplicates_and_serves_ranges(tmp_path):
    c=workspace(tmp_path)
    data=video_bytes(tmp_path)
    response=c.post('/api/media/import',files={'file':('../../movie.mp4',data,'video/mp4')})
    assert response.status_code==201
    media=response.json()['media']
    assert media['name']=='movie.mp4'
    assert Path(media['path']).is_relative_to(tmp_path/'artifacts/media')
    assert Path(media['path']).read_bytes()==data
    assert c.get(media['url'],headers={'Range':'bytes=0-9'}).status_code==206
    assert c.post('/api/media/import',files={'file':('renamed.mp4',data)}).json()['duplicate']
    assert len(list((tmp_path/'artifacts/media').iterdir()))==1
    restarted=workspace(tmp_path)
    assert len(restarted.get('/api/local-media').json())==1
    assert restarted.get('/api/workspace/setup').json()['initialized']


def test_invalid_upload_keeps_workspace_unchanged(tmp_path):
    c=workspace(tmp_path)
    for name in ('fake.mp4','wrong.ts'):
        assert c.post('/api/media/import',files={'file':(name,b'not video')}).status_code==422
    assert c.get('/api/local-media').json()==[]
    assert not c.get('/api/workspace/setup').json()['initialized']
    assert list((tmp_path/'artifacts/media').iterdir())==[]


def test_default_import_does_not_overwrite_edits(tmp_path):
    bundle=tmp_path/'bundle';bundle.mkdir()
    (bundle/'clip.mp4').write_bytes(b'fixture')
    item={'item_id':'person.test','category':'person','classification':'测试','name':'人物','aliases':[],
          'definition':'初始说明','status':'draft','materials':[]}
    task={'task_id':'task1','name':'默认任务','asset_path':'clip.mp4','object_ids':['person.test'],
          'status':'needs_review','purpose':'validation','capabilities':['face'],
          'result':{'events':[], 'metrics':{'coverage_complete':True}}}
    (bundle/'seed.json').write_text(json.dumps({'library_items':[item],'review_tasks':[task]}))
    (bundle/'catalog.json').write_text(json.dumps([{'media_id':'clip','name':'视频','path':'clip.mp4','url':'/bundled/clip.mp4'}]))
    c=workspace(tmp_path,bundle)
    assert c.post('/api/workspace/import-defaults').json()['added']=={'objects':1,'tasks':1,'media':1}
    assert c.post('/api/library-items/person.test/lifecycle',json={'action':'disable','note':'用户停用'}).status_code==200
    item=c.get('/api/library-items').json()[0]
    item.update(definition='用户修改')
    assert c.put('/api/library-items/person.test',json=item).status_code==200
    assert c.post('/api/review-tasks/task1/complete').status_code==200
    assert c.post('/api/workspace/import-defaults').json()['added']=={'objects':0,'tasks':0,'media':0}
    assert c.get('/api/library-items').json()[0]['definition']=='用户修改'
    assert c.get('/api/review-tasks/task1').json()['status']=='completed'
    assert len(workspace(tmp_path,bundle).get('/api/local-media').json())==1


def test_existing_workspace_migration_preserves_catalog(tmp_path):
    (tmp_path/'state.json').write_text(json.dumps({'library_items':[],'review_tasks':[]}))
    catalog=[{'media_id':'old','path':'/original.mp4','name':'原视频'}]
    c=TestClient(create_app(state_file=tmp_path/'state.json',media_catalog=catalog,setup_enabled=True))
    assert c.get('/api/workspace/setup').json()['initialized']
    assert c.get('/api/local-media').json()==catalog
    assert json.loads((tmp_path/'state.json').read_text())['media_items']==catalog


def test_uploaded_default_clip_is_not_duplicated(tmp_path):
    bundle=tmp_path/'bundle';bundle.mkdir()
    data=video_bytes(tmp_path)
    (bundle/'clip.mp4').write_bytes(data)
    (bundle/'seed.json').write_text(json.dumps({'library_items':[],'review_tasks':[]}))
    (bundle/'catalog.json').write_text(json.dumps([{'media_id':'clip','name':'内置片段','path':'clip.mp4','url':'/bundled/clip.mp4'}]))
    c=workspace(tmp_path,bundle)
    assert c.post('/api/workspace/import-defaults').status_code==200
    assert c.post('/api/media/import',files={'file':('same.mp4',data)}).json()['duplicate']
    assert len(c.get('/api/local-media').json())==1
