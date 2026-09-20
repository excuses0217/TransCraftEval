from pathlib import Path
import numpy as np
from face_watch.review_runner import consolidate_review_events, run_review


class FakeAnalyzer:
    def _read_image(self, path):
        return np.ones((16,16,3), dtype=np.uint8)

    def _detect_faces(self, image):
        if image.shape[0] == 16:
            return [np.array([0,0,10,10])]
        return [np.array([1,1,12,12]), np.array([30,1,12,12])]

    def _feature(self, image, face):
        return np.array([1.,0.], dtype=np.float32)


def test_two_simultaneous_faces_never_merge_and_evidence_is_written(tmp_path, monkeypatch):
    class Capture:
        index=0
        def isOpened(self): return True
        def get(self, key):
            import cv2
            return 1 if key == cv2.CAP_PROP_FPS else 3
        def read(self):
            self.index+=1
            return (True,np.zeros((64,64,3),dtype=np.uint8)) if self.index<=3 else (False,None)
        def release(self): pass
    monkeypatch.setattr('face_watch.review_runner.cv2.VideoCapture', lambda _:Capture())
    reference=tmp_path/'ref.bin'
    reference.write_bytes(b'test reference')
    result=run_review(FakeAnalyzer(),tmp_path/'video', [{'id':'p','name':'test','paths':[reference]}],tmp_path/'out',lambda _:None)
    assert len(result['events'])==2
    assert all(e['support_frames']==3 for e in result['events'])
    assert all(e['review_status']=='pending' for e in result['events'])
    assert result['metrics']['raw_hits']==6
    assert result['metrics']['coverage_complete'] is True
    snapshot_material=result['reference_snapshot'][0]['materials'][0]
    assert snapshot_material['title']=='ref.bin'
    assert snapshot_material['material_id'].startswith('ref.')
    assert snapshot_material['status']=='imported'
    assert snapshot_material['local_uri'].startswith('/artifacts/out/reference-')
    assert len(list((tmp_path/'out').glob('*.jpg')))==2


def test_adjacent_tracks_become_one_review_event_without_inventing_evidence():
    events = [
        {'event_id':'a','person_id':'p','person_name':'演员','start_seconds':1,'end_seconds':1,'support_frames':1,'best_score':.5,'review_status':'pending'},
        {'event_id':'b','person_id':'p','person_name':'演员','start_seconds':5,'end_seconds':5,'support_frames':1,'best_score':.6,'review_status':'pending'},
    ]
    grouped = consolidate_review_events(events, gap_seconds=4)
    assert len(grouped) == 1
    assert grouped[0]['event_id'] == 'a'
    assert grouped[0]['start_seconds'] == 1
    assert grouped[0]['end_seconds'] == 5
    assert [(s['start_seconds'],s['end_seconds']) for s in grouped[0]['segments']] == [(1,1),(5,5)]
    assert grouped[0]['segment_count'] == 2
    assert grouped[0]['support_frames'] == 2


def test_consolidation_preserves_human_work_and_simultaneous_tracks():
    reviewed = [
        {'event_id':'a','person_id':'p','start_seconds':1,'end_seconds':2,'review_status':'confirmed','reason':'appearance','history':[{'previous':'pending'}]},
        {'event_id':'b','person_id':'p','start_seconds':3,'end_seconds':4,'review_status':'confirmed','reason':'appearance','history':[{'previous':'pending'}]},
    ]
    merged = consolidate_review_events(reviewed, 2)
    assert merged[0]['review_status'] == 'confirmed'
    assert merged[0]['reason'] == 'appearance'
    assert len(merged[0]['history']) == 2

    simultaneous = [
        {'event_id':'a','person_id':'p','start_seconds':0,'end_seconds':2,'review_status':'pending'},
        {'event_id':'b','person_id':'p','start_seconds':0,'end_seconds':2,'review_status':'pending'},
    ]
    assert len(consolidate_review_events(simultaneous, 4)) == 2
