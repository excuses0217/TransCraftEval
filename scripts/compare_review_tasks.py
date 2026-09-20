#!/usr/bin/env python3
"""Compare two immutable review-task results without treating either as truth."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def interval_distance(first: dict, second: dict) -> float:
    first_start = float(first.get('start_seconds', 0))
    first_end = float(first.get('end_seconds', first_start))
    second_start = float(second.get('start_seconds', 0))
    second_end = float(second.get('end_seconds', second_start))
    if first_end < second_start:
        return second_start-first_end
    if second_end < first_start:
        return first_start-second_end
    return 0.0


def has_nearby_match(event: dict, others: list[dict], tolerance: float) -> bool:
    identity = event.get('person_id') or event.get('person_name')
    return any(
        (other.get('person_id') or other.get('person_name')) == identity
        and interval_distance(event, other) <= tolerance
        for other in others
    )


def nearby_matches(event: dict, others: list[dict], tolerance: float) -> list[dict]:
    identity = event.get('person_id') or event.get('person_name')
    return [
        other for other in others
        if (other.get('person_id') or other.get('person_name')) == identity
        and interval_distance(event, other) <= tolerance
    ]


def summarize(task: dict) -> dict:
    result = task.get('result') or {}
    events = result.get('events') or []
    metrics = result.get('metrics') or {}
    return {
        'task_id': task['task_id'],
        'name': task['name'],
        'analysis_profile': task.get('analysis_profile'),
        'events': len(events),
        'people': dict(sorted(Counter(event.get('person_name', '') for event in events).items())),
        'accepted_tracks': metrics.get('accepted_tracks'),
        'merged_track_fragments': metrics.get('merged_track_fragments'),
        'multi_segment_events': metrics.get('multi_segment_events'),
        'scene_count': metrics.get('scene_count'),
        'elapsed_seconds': metrics.get('elapsed_seconds'),
    }


def event_summary(event: dict) -> dict:
    return {
        'event_id': event.get('event_id'),
        'person_name': event.get('person_name'),
        'start_seconds': event.get('start_seconds'),
        'end_seconds': event.get('end_seconds'),
        'segment_count': event.get('segment_count', 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('baseline_task_id')
    parser.add_argument('candidate_task_id')
    parser.add_argument('--state', type=Path, default=ROOT/'data/showcase/state.json')
    parser.add_argument('--tolerance', type=float, default=2.0)
    args = parser.parse_args()
    state = json.loads(args.state.read_text(encoding='utf-8'))
    tasks = {task['task_id']:task for task in state['review_tasks']}
    baseline = tasks[args.baseline_task_id]
    candidate = tasks[args.candidate_task_id]
    baseline_events = (baseline.get('result') or {}).get('events') or []
    candidate_events = (candidate.get('result') or {}).get('events') or []
    if not baseline_events or not candidate_events:
        raise SystemExit('两个任务都必须已经生成事件结果')

    baseline_matched = sum(has_nearby_match(event, candidate_events, args.tolerance) for event in baseline_events)
    candidate_matched = sum(has_nearby_match(event, baseline_events, args.tolerance) for event in candidate_events)
    output = {
        'warning': '时间邻近一致性不是人工真值，不能据此计算准确率或召回率。',
        'tolerance_seconds': args.tolerance,
        'baseline': summarize(baseline),
        'candidate': summarize(candidate),
        'baseline_events_with_nearby_candidate': baseline_matched,
        'baseline_temporal_coverage': baseline_matched/len(baseline_events),
        'candidate_events_with_nearby_baseline': candidate_matched,
        'candidate_temporal_agreement': candidate_matched/len(candidate_events),
        'event_count_change': len(candidate_events)-len(baseline_events),
        'baseline_only_events': [
            event_summary(event)
            for event in baseline_events
            if not has_nearby_match(event, candidate_events, args.tolerance)
        ],
        'candidate_only_events': [
            event_summary(event)
            for event in candidate_events
            if not has_nearby_match(event, baseline_events, args.tolerance)
        ],
        'baseline_events_split_in_candidate': [
            {
                **event_summary(event),
                'candidate_events': [event_summary(match) for match in matches],
            }
            for event in baseline_events
            if len(matches := nearby_matches(event, candidate_events, args.tolerance)) > 1
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
