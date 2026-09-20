"""Scene-aware, track-level face retrieval for local video review.

Frame detections are deliberately kept separate from reviewer-facing events.
Identity is assigned only after a face track has collected multiple frames.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4
import hashlib
import math
import shutil
import time

import cv2
import numpy as np

from .multi_reference import ReferenceEmbedding, PersonGallery, PersonPolicy, score_person
from .review_runner import consolidate_review_events
from .confidence import attach_event_confidence


@dataclass(frozen=True)
class TrackPolicy:
    candidate_threshold: float = .35
    short_min_score: float = .55
    short_min_support: int = 3
    short_min_margin: float = .08
    short_min_topk: float = .45
    long_min_score: float = .46
    long_min_support: int = 8
    long_min_margin: float = .10
    long_min_topk: float = .44
    merge_gap_seconds: float = 1.5
    merge_face_similarity: float = .50
    merge_adjacent_scene_gap_seconds: float = 1.25
    merge_adjacent_scene_face_similarity: float = .72
    merge_adjacent_scene_visual_similarity: float = .82


PRECISION_TRACK_POLICY = TrackPolicy()
BALANCED_TRACK_POLICY = TrackPolicy(
    short_min_score=.50, short_min_support=2, short_min_margin=.06, short_min_topk=.42,
    long_min_score=.44, long_min_support=6, long_min_margin=.08, long_min_topk=.42,
)
RECALL_TRACK_POLICY = TrackPolicy(
    short_min_score=.45, short_min_support=2, short_min_margin=.04, short_min_topk=.40,
    long_min_score=.42, long_min_support=4, long_min_margin=.06, long_min_topk=.40,
)


@dataclass
class FaceObservation:
    timestamp: float
    box: np.ndarray
    feature: np.ndarray
    quality: float
    visual_feature: np.ndarray | None = None
    environment: dict[str, float] = field(default_factory=dict)


@dataclass
class FaceTrack:
    track_id: str
    scene_id: int
    observations: list[FaceObservation] = field(default_factory=list)

    @property
    def start(self) -> float:
        return self.observations[0].timestamp

    @property
    def end(self) -> float:
        return self.observations[-1].timestamp

    @property
    def last(self) -> FaceObservation:
        return self.observations[-1]


def _normalize(feature: np.ndarray) -> np.ndarray:
    value = np.asarray(feature, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(value))
    if norm <= 0 or not np.isfinite(norm):
        raise ValueError('invalid face feature')
    return value / norm


def _iou(first: np.ndarray, second: np.ndarray) -> float:
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right = min(first[0] + first[2], second[0] + second[2])
    bottom = min(first[1] + first[3], second[1] + second[3])
    intersection = max(0.0, right-left) * max(0.0, bottom-top)
    union = first[2]*first[3] + second[2]*second[3] - intersection
    return float(intersection / union) if union > 0 else 0.0


def frame_signature(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    small = cv2.resize(frame, (64, 36), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray_histogram = cv2.calcHist([gray], [0], None, [32], [0, 256]).reshape(-1)
    gray_histogram /= max(float(gray_histogram.sum()), 1.0)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    color_histogram = cv2.calcHist([hsv], [0, 1], None, [8, 4], [0, 180, 0, 256]).reshape(-1)
    color_histogram /= max(float(color_histogram.sum()), 1.0)
    return gray, gray_histogram, color_histogram, float(gray.mean())


def frame_visual_feature(frame: np.ndarray) -> np.ndarray:
    """Compact whole-frame context used only for nearby event merging."""
    small = cv2.resize(frame, (96, 54), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [8, 4], [0, 180, 0, 256]).reshape(-1)
    total = float(histogram.sum())
    if total > 0:
        histogram /= total
    return histogram.astype(np.float32)


def _visual_similarity(first: np.ndarray | None, second: np.ndarray | None) -> float:
    if first is None or second is None:
        return 0.0
    return float(np.minimum(first, second).sum())


def is_scene_cut(previous, current) -> bool:
    if previous is None:
        return False
    previous_gray, previous_gray_histogram, previous_color_histogram, previous_mean = previous
    gray, gray_histogram, color_histogram, mean = current
    pixel_change = float(np.mean(cv2.absdiff(previous_gray, gray))) / 255.0
    gray_overlap = float(np.minimum(previous_gray_histogram, gray_histogram).sum())
    color_overlap = float(np.minimum(previous_color_histogram, color_histogram).sum())
    black_transition = min(previous_mean, mean) < 8 and abs(previous_mean-mean) > 12
    return bool(
        black_transition
        or pixel_change > .17
        or (pixel_change > .13 and gray_overlap < .82)
        or (pixel_change > .11 and color_overlap < .72)
    )


def face_quality_signals(frame: np.ndarray, face: np.ndarray) -> dict[str, float]:
    height, width = frame.shape[:2]
    x, y, box_width, box_height = map(int, face[:4])
    x, y = max(0, x), max(0, y)
    crop = frame[y:min(height, y+max(1, box_height)), x:min(width, x+max(1, box_width))]
    if crop.size == 0:
        return {"overall": .1, "sharpness": 0.0, "face_size": 0.0, "detector_confidence": 0.0, "exposure": 0.0, "frontalness": 0.0}
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    sharpness = math.log1p(float(cv2.Laplacian(gray, cv2.CV_32F).var()))
    sharpness_score = float(np.clip((sharpness-2.5)/3.5, 0, 1))
    size_score = float(np.clip(math.sqrt(max(1, box_width*box_height))/120, 0, 1))
    detector_score = float(np.clip(face[14], 0, 1)) if len(face) > 14 else .75
    mean_brightness = float(gray.mean()) / 255.0
    exposure_score = float(np.clip(1.0 - abs(mean_brightness - .5) / .5, 0, 1))
    frontalness = .65
    if len(face) >= 14:
        first_eye = np.asarray(face[4:6], dtype=np.float32)
        second_eye = np.asarray(face[6:8], dtype=np.float32)
        nose = np.asarray(face[8:10], dtype=np.float32)
        eye_distance = max(float(np.linalg.norm(first_eye-second_eye)), 1.0)
        horizontal_offset = abs(float(nose[0] - (first_eye[0]+second_eye[0])/2)) / eye_distance
        frontalness = float(np.clip(1.0-horizontal_offset/.45, 0, 1))
    overall = .25*size_score + .25*sharpness_score + .18*detector_score + .17*exposure_score + .15*frontalness
    return {
        "overall": round(overall, 4),
        "sharpness": round(sharpness_score, 4),
        "face_size": round(size_score, 4),
        "detector_confidence": round(detector_score, 4),
        "exposure": round(exposure_score, 4),
        "frontalness": round(frontalness, 4),
    }


def face_quality(frame: np.ndarray, face: np.ndarray) -> float:
    return face_quality_signals(frame, face)["overall"]


class TrackAssembler:
    def __init__(self, max_gap_seconds: float = 1.75) -> None:
        self.max_gap_seconds = max_gap_seconds
        self.active: list[FaceTrack] = []
        self.finished: list[FaceTrack] = []

    def reset_scene(self) -> None:
        self.finished.extend(self.active)
        self.active = []

    def update(self, scene_id: int, observations: list[FaceObservation]) -> None:
        if observations:
            now = observations[0].timestamp
            retained = []
            for track in self.active:
                if track.scene_id == scene_id and now-track.end <= self.max_gap_seconds:
                    retained.append(track)
                else:
                    self.finished.append(track)
            self.active = retained

        pairs = []
        for track_index, track in enumerate(self.active):
            for observation_index, observation in enumerate(observations):
                similarity = float(track.last.feature @ observation.feature)
                overlap = _iou(track.last.box, observation.box)
                if similarity < .35 or (overlap < .02 and similarity < .60):
                    continue
                pairs.append((.75*similarity + .25*overlap, track_index, observation_index))
        used_tracks, used_observations = set(), set()
        for _, track_index, observation_index in sorted(pairs, reverse=True):
            if track_index in used_tracks or observation_index in used_observations:
                continue
            self.active[track_index].observations.append(observations[observation_index])
            used_tracks.add(track_index)
            used_observations.add(observation_index)
        for index, observation in enumerate(observations):
            if index not in used_observations:
                self.active.append(FaceTrack(uuid4().hex, scene_id, [observation]))

    def finish(self) -> list[FaceTrack]:
        self.reset_scene()
        return sorted(self.finished, key=lambda track: track.start)


def aggregate_track_identity(
    track: FaceTrack,
    galleries: list[PersonGallery],
    score_policy: PersonPolicy,
) -> dict[str, object] | None:
    if not track.observations:
        return None
    ranked_observations = sorted(track.observations, key=lambda item: item.quality, reverse=True)
    selected = ranked_observations[:min(5, len(ranked_observations))]
    aggregate = _normalize(sum(item.feature*item.quality for item in selected))
    visual_features = [item.visual_feature for item in selected if item.visual_feature is not None]
    aggregate_visual = None
    if visual_features:
        aggregate_visual = np.mean(visual_features, axis=0).astype(np.float32)
        total = float(aggregate_visual.sum())
        if total > 0:
            aggregate_visual /= total
    aggregate_scores = sorted(
        (score_person(aggregate, gallery, score_policy) for gallery in galleries),
        key=lambda score: score.recall_score,
        reverse=True,
    )
    primary = aggregate_scores[0]
    runner_up = aggregate_scores[1] if len(aggregate_scores) > 1 else None
    frame_scores = []
    frame_winners: list[str] = []
    for observation in track.observations:
        scores = sorted(
            (score_person(observation.feature, gallery, score_policy) for gallery in galleries),
            key=lambda score: score.recall_score,
            reverse=True,
        )
        frame_winners.append(scores[0].person_id)
        target = next(score for score in scores if score.person_id == primary.person_id)
        frame_scores.append((target, observation))
    supporting = [row for row in frame_scores if row[0].recall_score >= score_policy.candidate_threshold]
    best_score, best_observation = max(frame_scores, key=lambda row: row[0].recall_score)
    margin = primary.recall_score-runner_up.recall_score if runner_up else 1.0
    target_values = np.asarray(
        [score.recall_score for score, _ in frame_scores], dtype=np.float32
    )
    vote_ratio = frame_winners.count(primary.person_id) / len(frame_winners)
    independent_support = 0
    previous_support_time = -math.inf
    for score, observation in sorted(frame_scores, key=lambda row: row[1].timestamp):
        if (
            score.recall_score >= score_policy.candidate_threshold
            and observation.timestamp - previous_support_time >= .5
        ):
            independent_support += 1
            previous_support_time = observation.timestamp

    ordered_winners = [
        winner
        for _, winner in sorted(
            zip((item.timestamp for item in track.observations), frame_winners)
        )
    ]
    midpoint = max(1, len(ordered_winners) // 2)

    def dominant(values: list[str]) -> str | None:
        if not values:
            return None
        return max(set(values), key=lambda value: (values.count(value), value))

    early_winner = dominant(ordered_winners[:midpoint])
    late_winner = dominant(ordered_winners[midpoint:])
    early_late_consistent = (
        early_winner == primary.person_id
        and (late_winner is None or late_winner == primary.person_id)
    )
    adjacent_similarities = [
        float(first.feature @ second.feature)
        for first, second in zip(track.observations, track.observations[1:])
    ]
    environment_signals = {
        key: round(float(np.median([item.environment.get(key, item.quality) for item in selected])), 4)
        for key in ("sharpness", "face_size", "detector_confidence", "exposure", "frontalness")
    }
    return {
        'person_id': primary.person_id,
        'start_seconds': round(track.start, 3),
        'end_seconds': round(track.end, 3),
        'support_frames': len(supporting),
        'track_frames': len(track.observations),
        'best_score': round(max(score.recall_score for score, _ in frame_scores), 5),
        'topk_score': round(primary.topk_mean_score, 5),
        'track_score': round(primary.recall_score, 5),
        'margin': round(margin, 5),
        'quality': round(sum(item.quality for item in selected)/len(selected), 4),
        'environment_signals': environment_signals,
        'vote_ratio': round(vote_ratio, 5),
        'score_median': round(float(np.median(target_values)), 5),
        'score_p25': round(float(np.quantile(target_values, .25)), 5),
        'independent_support': independent_support,
        'early_late_consistent': early_late_consistent,
        'track_cohesion': round(
            float(np.median(adjacent_similarities)) if adjacent_similarities else 1.0,
            5,
        ),
        'evidence_seconds': round(best_observation.timestamp, 3),
        '_evidence_box': best_observation.box,
        'scene_id': track.scene_id,
        'track_id': track.track_id,
        '_track_feature': aggregate,
        '_visual_feature': aggregate_visual,
    }


def passes_track_policy(candidate: dict[str, object], policy: TrackPolicy) -> bool:
    score = float(candidate.get('best_score') or -1)
    support = int(candidate.get('support_frames') or 0)
    margin = float(candidate.get('margin') or -1)
    topk = float(candidate.get('topk_score') or -1)
    short = score >= policy.short_min_score and support >= policy.short_min_support and margin >= policy.short_min_margin and topk >= policy.short_min_topk
    long = score >= policy.long_min_score and support >= policy.long_min_support and margin >= policy.long_min_margin and topk >= policy.long_min_topk
    return short or long


def can_merge_continuous_tracks(previous: dict[str, object], current: dict[str, object], policy: TrackPolicy) -> bool:
    """Join only nearby fragments of one continuous on-screen appearance."""
    previous_end = float(previous.get('end_seconds') or previous.get('start_seconds') or 0)
    current_start = float(current.get('start_seconds') or 0)
    gap = current_start-previous_end
    if gap < 0 or gap > policy.merge_gap_seconds:
        return False

    previous_face = previous.get('_track_feature')
    current_face = current.get('_track_feature')
    if previous_face is None or current_face is None:
        return False
    face_similarity = float(np.asarray(previous_face) @ np.asarray(current_face))
    visual_similarity = _visual_similarity(previous.get('_visual_feature'), current.get('_visual_feature'))
    previous_scene = int(previous.get('scene_id', -1))
    current_scene = int(current.get('scene_id', -1))

    if previous_scene == current_scene:
        return face_similarity >= policy.merge_face_similarity

    # Only tolerate an adjacent, likely false-positive shot boundary.  Similar
    # pictures later in the programme remain separate review events.
    return (
        current_scene == previous_scene+1
        and gap <= policy.merge_adjacent_scene_gap_seconds
        and face_similarity >= policy.merge_adjacent_scene_face_similarity
        and visual_similarity >= policy.merge_adjacent_scene_visual_similarity
    )


def consolidate_continuous_track_events(events: list[dict[str, object]], policy: TrackPolicy):
    merged = consolidate_review_events(
        events,
        gap_seconds=policy.merge_gap_seconds,
        can_merge=lambda previous, current: can_merge_continuous_tracks(previous, current, policy),
    )
    for event in merged:
        event.pop('_track_feature', None)
        event.pop('_visual_feature', None)
        event['merge_scope'] = 'continuous_appearance'
        attach_event_confidence(event)
    return merged


def _write_evidence(candidate: dict[str, object], output: Path, event_id: str, video: Path) -> str:
    capture = cv2.VideoCapture(str(video))
    try:
        capture.set(cv2.CAP_PROP_POS_MSEC, float(candidate['evidence_seconds'])*1000)
        ok, image = capture.read()
    finally:
        capture.release()
    if not ok or image is None:
        raise ValueError('无法从原始媒资回读证据帧')
    x, y, width, height = map(int, candidate.pop('_evidence_box')[:4])
    cv2.rectangle(image, (x, y), (x+width, y+height), (52, 211, 153), 3)
    ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise ValueError('证据图编码失败')
    encoded.tofile(output/f'{event_id}.jpg')
    return f'/artifacts/{output.name}/{event_id}.jpg'


def run_track_review(analyzer, video: Path, people, output: Path, progress, interval=.5, policy=PRECISION_TRACK_POLICY, include_diagnostics=False):
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    score_policy = PersonPolicy(policy.candidate_threshold, .5, .03)
    galleries, names, reference_counts, snapshot = [], {}, {}, []
    for person in people:
        references, hashes, materials = [], [], []
        source_materials = person.get('materials') or [{} for _ in person['paths']]
        for path, source_material in zip(person['paths'], source_materials):
            image = analyzer._read_image(path)
            faces = analyzer._detect_faces(image)
            if len(faces) != 1:
                if person.get('skip_invalid_references'):
                    continue
                raise ValueError(f"{person['name']}参考图须包含一张可检测人脸：{path.name}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            references.append(ReferenceEmbedding(analyzer._feature(image, faces[0]), cluster_id=digest))
            hashes.append(digest)
            filename = f'reference-{digest}{path.suffix}'
            shutil.copy2(path, output/filename)
            materials.append({'material_id':source_material.get('material_id',f'ref.{digest}'),'kind':'reference_image','title':source_material.get('title',path.name),'local_uri':f'/artifacts/{output.name}/{filename}','quality_note':source_material.get('quality_note','任务创建时保存的参考照片。'),'status':source_material.get('status','imported')})
        if not references:
            raise ValueError(f"{person['name']}没有通过质检的参考图")
        galleries.append(PersonGallery(person['id'], tuple(references)))
        names[person['id']] = person['name']
        reference_counts[person['id']] = len(references)
        snapshot.append({'person_id':person['id'],'name':person['name'],'reference_count':len(references),'reference_hashes':hashes,'materials':materials})

    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError('无法打开本地媒资')
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not np.isfinite(fps) or fps <= 0:
        raise ValueError('无法读取有效帧率')
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    assembler = TrackAssembler(max_gap_seconds=max(1.75, interval*2.25))
    previous_signature = None
    scene_id = index = sampled = detected_faces = 0
    next_time = 0.0
    scene_sample_seconds = min(.25, interval)
    next_scene_time = 0.0
    last_scene_cut = -math.inf
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp = index/fps
            index += 1
            if timestamp >= next_scene_time:
                next_scene_time += scene_sample_seconds
                signature = frame_signature(frame)
                if is_scene_cut(previous_signature, signature) and timestamp-last_scene_cut >= .75:
                    scene_id += 1
                    last_scene_cut = timestamp
                    assembler.reset_scene()
                previous_signature = signature
            if timestamp < next_time:
                continue
            next_time += interval
            sampled += 1
            visual_feature = frame_visual_feature(frame)
            faces = analyzer._detect_faces(frame)
            detected_faces += len(faces)
            observations = []
            for face in faces:
                quality_signals = face_quality_signals(frame, face)
                observations.append(FaceObservation(timestamp, face[:4].copy(), analyzer._feature(frame, face), quality_signals['overall'], visual_feature, quality_signals))
            assembler.update(scene_id, observations)
            progress({'progress':min(.99,index/total) if total else 0,'sampled_frames':sampled,'detected_faces':detected_faces,'track_count':len(assembler.finished)+len(assembler.active),'scanned_seconds':round(timestamp,1)})
    finally:
        capture.release()
    if index == 0:
        raise ValueError('未能解码任何帧')

    tracks = assembler.finish()
    candidates = [aggregate_track_identity(track, galleries, score_policy) for track in tracks]
    candidates = [candidate for candidate in candidates if candidate and float(candidate['best_score']) >= policy.candidate_threshold]
    accepted = [candidate for candidate in candidates if passes_track_policy(candidate, policy)]
    events = []
    for candidate in accepted:
        event_id = uuid4().hex
        candidate.update(event_id=event_id, person_name=names[candidate['person_id']], reference_count=reference_counts[candidate['person_id']], review_status='pending', note='', history=[], ambiguous=False)
        candidate['evidence_image'] = _write_evidence(candidate, output, event_id, video)
        attach_event_confidence(candidate)
        events.append(candidate)
    events = consolidate_continuous_track_events(events, policy)
    complete = total > 0 and index >= total-max(2,int(fps))
    result = {'events':events,'metrics':{'sampled_frames':sampled,'detected_faces':detected_faces,'raw_tracks':len(tracks),'candidate_tracks':len(candidates),'accepted_tracks':len(accepted),'review_events':len(events),'merged_track_fragments':len(accepted)-len(events),'multi_segment_events':sum(int(event.get('segment_count',1))>1 for event in events),'event_merge_scope':'continuous_appearance','event_merge_gap_seconds':policy.merge_gap_seconds,'adjacent_scene_merge_gap_seconds':policy.merge_adjacent_scene_gap_seconds,'decoded_frames':index,'expected_frames':total,'duration_seconds':round(index/fps,2),'sample_seconds':interval,'scene_sample_seconds':scene_sample_seconds,'scene_count':scene_id+1,'coverage_complete':complete,'elapsed_seconds':round(time.monotonic()-started,2)},'reference_snapshot':snapshot,'method':'YuNet + SFace / 高频轻量镜头检测 / 镜头内人脸跟踪 / 质量加权多帧融合 / 开放集门控 / 连续出镜事件归并','validation_note':'轨迹级算法候选，仍需独立标注验证身份阈值与连续事件归并阈值。'}
    if include_diagnostics:
        result['_merge_candidates'] = [
            {
                **{key:value for key,value in candidate.items() if key != '_evidence_box'},
                'person_name': names[candidate['person_id']],
                'event_id': candidate['track_id'],
                'review_status': 'pending',
                'note': '',
                'history': [],
                'ambiguous': False,
            }
            for candidate in candidates
        ]
        result['track_candidates'] = [
            {
                **{key:value for key,value in candidate.items() if not key.startswith('_')},
                'person_name': names[candidate['person_id']],
                'event_id': candidate['track_id'],
            }
            for candidate in candidates
        ]
    return result
