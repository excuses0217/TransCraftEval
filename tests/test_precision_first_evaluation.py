from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/evaluate_precision_first.py"
SPEC = importlib.util.spec_from_file_location("evaluate_precision_first", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def event(person: str, start: float, end: float, score: float = 0.6) -> dict[str, object]:
    return {
        "event_id": f"{person}-{start}",
        "person_id": person,
        "person_name": person,
        "start_seconds": start,
        "end_seconds": end,
        "best_score": score,
        "topk_score": score - 0.05,
        "margin": 0.12,
        "support_frames": 4,
    }


def test_policy_gate_checks_track_and_open_set_evidence() -> None:
    policy = MODULE.Policy("precision", 0.6, 3, 0.08, 0.5)
    assert MODULE.passes(event("p", 0, 1, 0.65), policy)
    too_short = event("p", 0, 1, 0.65)
    too_short["support_frames"] = 2
    assert not MODULE.passes(too_short, policy)
    ambiguous = event("p", 0, 1, 0.65)
    ambiguous["margin"] = 0.02
    assert not MODULE.passes(ambiguous, policy)


def test_long_track_fallback_recovers_consistent_lower_score() -> None:
    policy = MODULE.Policy("adaptive", 0.55, 3, 0.08, 0.45, 0.46, 8, 0.12, 0.46)
    long_track = event("p", 0, 3, 0.48)
    long_track["support_frames"] = 12
    long_track["topk_score"] = 0.48
    assert MODULE.passes(long_track, policy)
    long_track["support_frames"] = 4
    assert not MODULE.passes(long_track, policy)


def test_merge_preserves_subsegments_and_does_not_bridge_long_gap() -> None:
    groups = MODULE.merge_events(
        [event("p", 0, 1), event("p", 2, 3), event("p", 8, 9)], 1.5
    )
    assert len(groups) == 2
    assert groups[0]["start_seconds"] == 0
    assert groups[0]["end_seconds"] == 3
    assert len(groups[0]["segments"]) == 2
    assert len(groups[1]["segments"]) == 1


def test_merge_never_combines_different_people() -> None:
    groups = MODULE.merge_events([event("a", 0, 2), event("b", 1, 3)], 5)
    assert len(groups) == 2
