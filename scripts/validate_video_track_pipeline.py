#!/usr/bin/env python3
"""Run the scene-aware track pipeline against the current blind-label batch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from face_watch.opencv_analyzer import AnalyzerConfig, OpenCvAnalyzer
from face_watch.video_track_runner import (
    BALANCED_TRACK_POLICY,
    PRECISION_TRACK_POLICY,
    RECALL_TRACK_POLICY,
    consolidate_continuous_track_events,
    passes_track_policy,
    run_track_review,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT/'data/showcase/state.json'
DEFAULT_MANIFEST = ROOT/'output/precision_first_validation/blind_batch_v2/private_manifest.json'
DEFAULT_OUTPUT = ROOT/'output/precision_first_validation/video_track_v2'
DEFAULT_TASK_ID = '1f424c07aeff4170b9d2a12d0476e8e3'


def resolve_reference(uri: str) -> Path | None:
    if uri.startswith('/bundled/'):
        return ROOT/'showcase_bundle'/uri[len('/bundled/'):]
    if uri.startswith('/assets/'):
        return ROOT/'frontend_dist'/uri.lstrip('/')
    if uri.startswith('/artifacts/'):
        return ROOT/'artifacts/showcase'/uri[len('/artifacts/'):]
    path = Path(uri)
    return path if path.is_absolute() else ROOT/path


def build_people(state, task):
    items = {item['item_id']:item for item in state['library_items']}
    people = []
    for object_id in task['object_ids']:
        item = items[object_id]
        paths, materials = [], []
        for material in item.get('materials', []):
            if material.get('kind') != 'reference_image' or material.get('status') == 'disabled':
                continue
            path = resolve_reference(str(material.get('local_uri', '')))
            if path and path.is_file():
                paths.append(path)
                materials.append(material)
        if paths:
            people.append({'id':object_id,'name':item['name'],'paths':paths,'materials':materials,'skip_invalid_references':True})
    return people


def events_in_clip(events, clip):
    start, end = float(clip['start_seconds']), float(clip['end_seconds'])
    return [event for event in events if start <= float(event.get('evidence_seconds',event.get('start_seconds',0))) <= end]


def evaluate(events, manifest):
    rows = []
    for clip in manifest['clips']:
        source = clip['source']
        expected = str(source['source_person'])
        clip_events = events_in_clip(events, clip)
        matches = [event for event in clip_events if event.get('person_name') == expected]
        rows.append({'clip_id':clip['clip_id'],'kind':source['kind'],'expected_person':expected,'events':len(clip_events),'event_people':sorted({event.get('person_name') for event in clip_events}),'expected_events':len(matches),'expected_survives':bool(matches)})
    positives = [row for row in rows if row['kind'] != 'cross_film_hard_negative']
    negatives = [row for row in rows if row['kind'] == 'cross_film_hard_negative']
    return {'clips':len(rows),'positive_clips':len(positives),'positive_expected_survives':sum(row['expected_survives'] for row in positives),'hard_negative_clips':len(negatives),'hard_negative_source_survives':sum(row['expected_survives'] for row in negatives),'events':len(events),'rows':rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--task-id', default=DEFAULT_TASK_ID)
    parser.add_argument('--interval', type=float, default=.5)
    parser.add_argument('--policy', choices=('precision','balanced','recall'), default='precision')
    args = parser.parse_args()
    state = json.loads(args.state.read_text(encoding='utf-8'))
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    task = next(task for task in state['review_tasks'] if task['task_id'] == args.task_id)
    people = build_people(state, task)
    args.output.mkdir(parents=True, exist_ok=True)
    analyzer = OpenCvAnalyzer(AnalyzerConfig(detector_model=ROOT/'models/face_detection_yunet_2023mar.onnx',recognizer_model=ROOT/'models/face_recognition_sface_2021dec.onnx',output_dir=args.output,detection_score_threshold=.65,max_detection_side=960))
    latest = {'scanned_seconds':0}
    def progress(values):
        nonlocal latest
        latest = values
        if int(float(values.get('scanned_seconds',0))) % 30 == 0:
            print(json.dumps({'progress':values.get('progress'),'scanned_seconds':values.get('scanned_seconds'),'tracks':values.get('track_count')},ensure_ascii=False),flush=True)
    policies = {
        'precision': PRECISION_TRACK_POLICY,
        'balanced': BALANCED_TRACK_POLICY,
        'recall': RECALL_TRACK_POLICY,
    }
    result = run_track_review(analyzer,Path(task['asset_path']),people,args.output/'artifacts',progress,interval=args.interval,policy=policies[args.policy],include_diagnostics=True)
    current_events = list((task.get('result') or {}).get('events', []))
    merge_candidates = result.pop('_merge_candidates')
    candidates = result.pop('track_candidates')
    policy_sweep = {}
    for name, policy in policies.items():
        accepted = [candidate for candidate in merge_candidates if passes_track_policy(candidate,policy)]
        grouped = consolidate_continuous_track_events(accepted,policy)
        policy_sweep[name] = evaluate(grouped,manifest)
    summary = {'pipeline':'scene-aware-track-v2','task_id':args.task_id,'metrics':result['metrics'],'policy_sweep':policy_sweep,'track_pipeline':evaluate(result['events'],manifest),'current_pipeline':evaluate(current_events,manifest),'track_candidates':candidates,'events':result['events']}
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:summary[key] for key in ('metrics','track_pipeline','current_pipeline')},ensure_ascii=False,indent=2,default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
