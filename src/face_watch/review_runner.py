"""Local multi-person candidate scan. No automatic identity confirmation."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import hashlib
import time
import shutil

import cv2
import numpy as np

from .multi_reference import ReferenceEmbedding, PersonGallery, PersonPolicy, score_person


def _segment_from_event(event):
    return {
        'event_id': event.get('event_id'),
        'start_seconds': float(event.get('start_seconds', 0)),
        'end_seconds': float(event.get('end_seconds', event.get('start_seconds', 0))),
        'evidence_seconds': event.get('evidence_seconds'),
        'evidence_image': event.get('evidence_image'),
        'support_frames': int(event.get('support_frames') or 0),
        'best_score': event.get('best_score'),
        'review_status': event.get('review_status', 'pending'),
        'scene_id': event.get('scene_id'),
        'track_id': event.get('track_id'),
    }


def _merged_review_status(events):
    statuses = [event.get('review_status', 'pending') for event in events]
    unique = set(statuses)
    if len(unique) == 1:
        return statuses[0]
    # Never turn a partly reviewed group into an automatic human confirmation.
    if 'pending' in unique:
        return 'uncertain' if unique <= {'pending', 'uncertain'} else 'pending'
    return 'uncertain'


def consolidate_review_events(events, gap_seconds=4.0, can_merge=None):
    """Build reviewer-sized appearances from short detector tracks.

    Every original interval remains available in ``segments``.  The outer
    start/end is only the review envelope, so a detector miss inside the gap
    is not rewritten as positive evidence.
    """
    ordered = sorted(
        (deepcopy(event) for event in events),
        key=lambda event: (
            str(event.get('person_id') or event.get('person_name') or ''),
            float(event.get('start_seconds') or 0),
        ),
    )
    grouped = []
    for event in ordered:
        start = float(event.get('start_seconds') or 0)
        end = float(event.get('end_seconds') or start)
        identity = str(event.get('person_id') or event.get('person_name') or '')
        previous = grouped[-1] if grouped else None
        same_identity = previous is not None and previous['_identity'] == identity
        close = same_identity and start - float(previous['end_seconds']) <= gap_seconds
        # Two tracks with the exact same lifetime usually represent different
        # simultaneous faces. Keep them separate instead of hiding a conflict.
        exact_overlap = bool(
            close
            and start == float(previous['start_seconds'])
            and end == float(previous['end_seconds'])
        )
        allowed = close and not exact_overlap
        if allowed and can_merge is not None:
            allowed = bool(can_merge(previous, event))
        if not allowed:
            event['_identity'] = identity
            event['_source_events'] = [deepcopy(event)]
            event['segments'] = list(event.get('segments') or [_segment_from_event(event)])
            event['segment_count'] = len(event['segments'])
            grouped.append(event)
            continue

        source_events = previous['_source_events']
        source_events.append(deepcopy(event))
        previous['start_seconds'] = min(float(previous['start_seconds']), start)
        previous['end_seconds'] = max(float(previous['end_seconds']), end)
        previous['support_frames'] = int(previous.get('support_frames') or 0) + int(event.get('support_frames') or 0)
        previous['independent_support'] = int(previous.get('independent_support') or 0) + int(event.get('independent_support') or 0)
        previous['ambiguous'] = bool(previous.get('ambiguous')) or bool(event.get('ambiguous'))
        previous['segments'].extend(event.get('segments') or [_segment_from_event(event)])
        previous['segment_count'] = len(previous['segments'])
        previous['merged_event_ids'] = [segment.get('event_id') for segment in previous['segments']]
        previous['review_status'] = _merged_review_status(source_events)
        if float(event.get('best_score') or -1) > float(previous.get('best_score') or -1):
            for key in (
                'best_score', 'evidence_seconds', 'evidence_image', 'margin', 'topk_score',
                'track_score', 'score_median', 'score_p25', 'quality', 'vote_ratio',
                'early_late_consistent', 'track_cohesion', 'environment_signals',
            ):
                if key in event:
                    previous[key] = event[key]
        previous['history'] = [
            item
            for source in source_events
            for item in (source.get('history') or [])
        ]
        # Continuity-aware callers compare the next fragment with the latest
        # fragment in this group, not only with the group's first keyframe.
        for key in ('_track_feature', '_visual_feature', 'scene_id'):
            if key in event:
                previous[key] = event[key]
        reasons = {source.get('reason') for source in source_events if source.get('reason')}
        notes = {source.get('note') for source in source_events if source.get('note')}
        previous['reason'] = reasons.pop() if len(reasons) == 1 else ''
        previous['note'] = notes.pop() if len(notes) == 1 else ''

    for event in grouped:
        event.pop('_identity', None)
        event.pop('_source_events', None)
        event.setdefault('merged_event_ids', [event['event_id']])
    return sorted(grouped, key=lambda event: float(event.get('start_seconds') or 0))


def run_review(analyzer, video, people, output, progress, interval=1.0):
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    policy = PersonPolicy(.35, .5, .03)
    galleries, snapshot = [], []
    for person in people:
        refs, hashes, accepted_paths, accepted_materials, rejected_references = [], [], [], [], []
        source_materials = person.get('materials') or [{} for _ in person['paths']]
        if len(source_materials) != len(person['paths']):
            source_materials = [{} for _ in person['paths']]
        for path, source_material in zip(person['paths'], source_materials):
            image = analyzer._read_image(path)
            faces = analyzer._detect_faces(image)
            if len(faces) != 1:
                if person.get('skip_invalid_references'):
                    rejected_references.append({'filename':path.name,'reason':'参考图须包含一张可检测人脸','detected_faces':len(faces)})
                    continue
                raise ValueError(f"{person['name']}参考图须包含一张可检测人脸：{path.name}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            refs.append(ReferenceEmbedding(analyzer._feature(image, faces[0]), cluster_id=digest))
            hashes.append(digest)
            accepted_paths.append(path)
            accepted_materials.append(source_material)
        if not refs:
            raise ValueError(f"{person['name']}没有通过质检的参考图，不能跳过该人物")
        galleries.append(PersonGallery(person['id'], tuple(refs)))
        materials=[]
        for path, digest, source_material in zip(accepted_paths, hashes, accepted_materials):
            filename=f'reference-{digest}{path.suffix}'
            shutil.copy2(path,output/filename)
            materials.append({
                'material_id': source_material.get('material_id', f'ref.{digest}'),
                'kind': 'reference_image',
                'title': source_material.get('title', path.name),
                'local_uri': f'/artifacts/{output.name}/{filename}',
                'quality_note': source_material.get('quality_note', '任务创建时保存的参考照片。'),
                'status': source_material.get('status', 'imported'),
            })
        snapshot.append({'person_id': person['id'], 'name': person['name'], 'reference_count': len(refs), 'reference_hashes': hashes, 'materials':materials, 'rejected_references':rejected_references})
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError('无法打开本地媒资')
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not np.isfinite(fps) or fps <= 0:
        capture.release()
        raise ValueError('无法读取有效帧率')
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    events, active = [], []
    index = sampled = face_count = hits = 0
    next_time = 0.0
    names = {p['id']: p['name'] for p in people}
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp = index / fps
            index += 1
            if timestamp < next_time:
                continue
            next_time += interval
            sampled += 1
            active = [t for t in active if timestamp - t['last'] <= interval * 1.5]
            used = set()
            for face in analyzer._detect_faces(frame):
                face_count += 1
                feature = analyzer._feature(frame, face)
                scores = sorted((score_person(feature, g, policy) for g in galleries), key=lambda s: s.recall_score, reverse=True)
                best = scores[0]
                if best.recall_score < policy.candidate_threshold:
                    continue
                hits += 1
                margin = best.recall_score - scores[1].recall_score if len(scores) > 1 else None
                ambiguous = margin is not None and margin < .03
                match = None
                # Spatial AND appearance continuity; never merge simultaneous faces.
                for track in active:
                    if track['event']['event_id'] in used or track['event']['person_id'] != best.person_id:
                        continue
                    a, b = face[:4], track['box']
                    left, top = max(a[0], b[0]), max(a[1], b[1])
                    right, bottom = min(a[0]+a[2], b[0]+b[2]), min(a[1]+a[3], b[1]+b[3])
                    intersection = max(0, right-left)*max(0, bottom-top)
                    union = a[2]*a[3]+b[2]*b[3]-intersection
                    if union > 0 and intersection/union > .15 and feature @ track['feature'] > .5:
                        match = track
                        break
                if match is None:
                    event = {'event_id': uuid4().hex, 'person_id': best.person_id, 'person_name': names[best.person_id], 'start_seconds': round(timestamp, 3), 'end_seconds': round(timestamp, 3), 'support_frames': 0, 'best_score': -1, 'review_status': 'pending', 'note': '', 'history': [], 'ambiguous': False}
                    match = {'event': event}
                    active.append(match)
                    events.append(event)
                event = match['event']
                used.add(event['event_id'])
                event['end_seconds'] = round(timestamp, 3)
                event['support_frames'] += 1
                event['ambiguous'] |= ambiguous
                if best.recall_score > event['best_score']:
                    event.update(best_score=round(best.recall_score, 5), evidence_seconds=round(timestamp, 3), margin=None if margin is None else round(margin, 5), topk_score=round(best.topk_mean_score, 5))
                    preview = frame.copy()
                    x, y, w, h = map(int, face[:4])
                    cv2.rectangle(preview, (x,y), (x+w,y+h), (52,211,153), 3)
                    ok, encoded = cv2.imencode('.jpg', preview)
                    if not ok:
                        raise ValueError('证据图编码失败')
                    encoded.tofile(output / f"{event['event_id']}.jpg")
                    event['evidence_image'] = f"/artifacts/{output.name}/{event['event_id']}.jpg"
                match.update(last=timestamp, box=face[:4].copy(), feature=feature)
            progress({'progress': min(.99, index/total) if total > 0 else 0, 'sampled_frames': sampled, 'detected_faces': face_count, 'candidate_count': len(events), 'scanned_seconds': round(timestamp, 1)})
    finally:
        capture.release()
    if index == 0:
        raise ValueError('未能解码任何帧')
    complete = total > 0 and index >= total - max(2, int(fps))
    raw_track_events = len(events)
    events = consolidate_review_events(events, gap_seconds=max(3.0, interval * 4))
    return {'events': events, 'metrics': {'sampled_frames': sampled, 'detected_faces': face_count, 'raw_hits': hits, 'raw_track_events': raw_track_events, 'review_events': len(events), 'decoded_frames': index, 'expected_frames': total, 'duration_seconds': round(index/fps, 2), 'sample_seconds': interval, 'coverage_complete': complete, 'elapsed_seconds': round(time.monotonic()-started, 2)}, 'reference_snapshot': snapshot, 'method': 'YuNet + SFace / 多图候选召回 / 空间与外观短时关联 / 相邻片段归并', 'validation_note': '候选尚未经独立标注；无法据此计算召回率。' if complete else '解码长度未通过完整性检查，结果仅覆盖已读取区间。'}
