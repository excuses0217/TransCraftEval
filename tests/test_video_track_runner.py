import cv2
import numpy as np

from face_watch.multi_reference import ReferenceEmbedding, PersonGallery, PersonPolicy
from face_watch.video_track_runner import (
    FaceObservation,
    FaceTrack,
    TrackAssembler,
    TrackPolicy,
    aggregate_track_identity,
    can_merge_continuous_tracks,
    consolidate_continuous_track_events,
    frame_visual_feature,
    frame_signature,
    is_scene_cut,
    passes_track_policy,
)


def observation(timestamp, x, feature):
    return FaceObservation(
        timestamp,
        np.array([x, 0, 20, 20], dtype=np.float32),
        np.asarray(feature, dtype=np.float32),
        .8,
    )


def merge_event(event_id, start, end, scene, face, visual):
    return {
        'event_id': event_id,
        'person_id': 'person.a',
        'start_seconds': start,
        'end_seconds': end,
        'scene_id': scene,
        'support_frames': 3,
        'best_score': .7,
        'review_status': 'pending',
        '_track_feature': np.asarray(face, dtype=np.float32),
        '_visual_feature': np.asarray(visual, dtype=np.float32),
    }


def test_scene_cut_detects_black_separator_but_not_small_change():
    first = np.full((90, 160, 3), 120, dtype=np.uint8)
    similar = np.full((90, 160, 3), 124, dtype=np.uint8)
    black = np.zeros((90, 160, 3), dtype=np.uint8)
    assert not is_scene_cut(frame_signature(first), frame_signature(similar))
    assert is_scene_cut(frame_signature(first), frame_signature(black))


def test_scene_cut_detects_structural_change_even_with_same_histogram():
    first = np.zeros((90, 160, 3), dtype=np.uint8)
    first[:, 80:] = 255
    reversed_frame = np.zeros((90, 160, 3), dtype=np.uint8)
    reversed_frame[:, :80] = 255
    assert is_scene_cut(frame_signature(first), frame_signature(reversed_frame))


def test_tracker_uses_face_continuity_before_identity_and_keeps_simultaneous_faces_separate():
    assembler = TrackAssembler(max_gap_seconds=2)
    assembler.update(0, [observation(0, 0, [1, 0]), observation(0, 60, [0, 1])])
    assembler.update(0, [observation(1, 2, [.99, .01]), observation(1, 62, [.01, .99])])
    tracks = assembler.finish()
    assert len(tracks) == 2
    assert sorted(len(track.observations) for track in tracks) == [2, 2]


def test_track_identity_aggregates_multiple_frames_and_applies_precision_gate():
    track = FaceTrack('track', 0, [
        observation(0, 0, [1, 0]),
        observation(.5, 1, [.98, .02]),
        observation(1, 2, [.96, .04]),
    ])
    galleries = [
        PersonGallery('a', (ReferenceEmbedding(np.array([1, 0], dtype=np.float32)),)),
        PersonGallery('b', (ReferenceEmbedding(np.array([0, 1], dtype=np.float32)),)),
    ]
    candidate = aggregate_track_identity(track, galleries, PersonPolicy(.35, .5, .03))
    assert candidate is not None
    assert candidate['person_id'] == 'a'
    assert candidate['support_frames'] == 3
    assert candidate['vote_ratio'] == 1
    assert candidate['score_p25'] > .95
    assert candidate['independent_support'] == 3
    assert candidate['early_late_consistent'] is True
    assert candidate['track_cohesion'] > .95
    assert passes_track_policy(candidate, TrackPolicy())
    candidate['support_frames'] = 1
    assert not passes_track_policy(candidate, TrackPolicy())


def test_track_identity_reports_frame_vote_disagreement():
    track = FaceTrack('mixed', 0, [
        observation(0, 0, [1, 0]),
        observation(.5, 1, [1, 0]),
        observation(1, 2, [0, 1]),
        observation(1.5, 3, [0, 1]),
    ])
    galleries = [
        PersonGallery('a', (ReferenceEmbedding(np.array([1, 0], dtype=np.float32)),)),
        PersonGallery('b', (ReferenceEmbedding(np.array([0, 1], dtype=np.float32)),)),
    ]
    candidate = aggregate_track_identity(track, galleries, PersonPolicy(.35, .5, .03))
    assert candidate is not None
    assert candidate['vote_ratio'] == .5
    assert candidate['early_late_consistent'] is False


def test_continuous_merge_joins_nearby_same_shot_fragments():
    policy = TrackPolicy()
    first = merge_event('a', 10, 11, 3, [1, 0], [.7, .3])
    second = merge_event('b', 12, 13, 3, [.98, .02], [.68, .32])
    assert can_merge_continuous_tracks(first, second, policy)
    merged = consolidate_continuous_track_events([first, second], policy)
    assert len(merged) == 1
    assert merged[0]['segment_count'] == 2
    assert merged[0]['merge_scope'] == 'continuous_appearance'
    assert '_track_feature' not in merged[0]


def test_continuous_merge_keeps_far_or_non_adjacent_scenes_separate():
    policy = TrackPolicy()
    first = merge_event('a', 10, 11, 3, [1, 0], [.7, .3])
    far = merge_event('b', 30, 31, 3, [1, 0], [.7, .3])
    later_scene = merge_event('c', 12, 13, 8, [1, 0], [.7, .3])
    assert not can_merge_continuous_tracks(first, far, policy)
    assert not can_merge_continuous_tracks(first, later_scene, policy)


def test_continuous_merge_never_joins_overlapping_faces():
    policy = TrackPolicy()
    first = merge_event('a', 10, 13, 3, [1, 0], [.7, .3])
    simultaneous = merge_event('b', 11, 12, 3, [1, 0], [.7, .3])
    assert not can_merge_continuous_tracks(first, simultaneous, policy)
    assert len(consolidate_continuous_track_events([first, simultaneous], policy)) == 2


def test_continuous_merge_requires_strong_evidence_across_adjacent_scene_boundary():
    policy = TrackPolicy()
    first = merge_event('a', 10, 11, 3, [1, 0], [.7, .3])
    strong = merge_event('b', 11.5, 12, 4, [.99, .01], [.69, .31])
    weak_picture = merge_event('c', 11.5, 12, 4, [.99, .01], [.1, .9])
    assert can_merge_continuous_tracks(first, strong, policy)
    assert not can_merge_continuous_tracks(first, weak_picture, policy)


def test_frame_visual_feature_is_compact_and_normalized():
    frame = np.full((90, 160, 3), (10, 80, 180), dtype=np.uint8)
    feature = frame_visual_feature(frame)
    assert feature.shape == (32,)
    assert np.isclose(feature.sum(), 1)
