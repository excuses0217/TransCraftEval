#!/usr/bin/env python3
"""Evaluate model gates against completed human decisions in a blind task."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmark_video_face_models import FIXED_DUAL_POLICIES, dual_gate_passes


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUMMARY = ROOT / "output/video_face_model_ab/summary.json"
DEFAULT_MANIFEST = ROOT / "output/precision_first_validation/blind_batch/private_manifest.json"
DEFAULT_STATE = ROOT / "data/showcase/state.json"
DEFAULT_OUTPUT = ROOT / "output/video_face_model_ab/human_label_evaluation.json"
DEFAULT_TASK_ID = "048cbf3fb31c4c96acf9893b1537b9c2"


def reviewed_groups(task: dict[str, object], manifest: dict[str, object]) -> list[dict[str, object]]:
    labels: list[dict[str, object]] = []
    for event in (task.get("result") or {}).get("events", []):
        status = str(event.get("review_status", "pending"))
        if status == "pending":
            continue
        evidence = float(event.get("evidence_seconds") or event.get("start_seconds") or 0)
        clip = next(
            (
                item
                for item in manifest["clips"]
                if float(item["start_seconds"]) <= evidence <= float(item["end_seconds"])
            ),
            None,
        )
        if clip is None:
            continue
        clip_start = float(clip["start_seconds"])
        clip_end = float(clip["end_seconds"])
        labels.append(
            {
                "clip_id": clip["clip_id"],
                "clip_path": clip["source"]["clip_path"],
                "media": clip["source"]["media"],
                "person_name": event["person_name"],
                "review_status": status,
                "start_seconds": max(0.0, float(event.get("start_seconds") or evidence) - clip_start),
                "end_seconds": min(
                    clip_end - clip_start,
                    float(event.get("end_seconds") or evidence) - clip_start,
                ),
                "source_event_ids": [event["event_id"]],
            }
        )

    groups: list[dict[str, object]] = []
    for label in sorted(
        labels,
        key=lambda item: (
            str(item["clip_path"]),
            str(item["person_name"]),
            str(item["review_status"]),
            float(item["start_seconds"]),
        ),
    ):
        same_identity = (
            groups
            and all(
                groups[-1][key] == label[key]
                for key in ("clip_path", "person_name", "review_status")
            )
        )
        # This evaluation asks whether an identity is present in one six-second
        # blind window.  Multiple historical frame events for the same person
        # therefore form one label even when the old runner fragmented them.
        if same_identity:
            groups[-1]["end_seconds"] = max(
                float(groups[-1]["end_seconds"]), float(label["end_seconds"])
            )
            groups[-1]["source_event_ids"].extend(label["source_event_ids"])
        else:
            groups.append(label)
    return groups


def overlaps(candidate: dict[str, object], label: dict[str, object]) -> bool:
    return (
        float(candidate.get("end_seconds") or candidate.get("start_seconds") or 0)
        >= float(label["start_seconds"]) - .75
        and float(candidate.get("start_seconds") or 0)
        <= float(label["end_seconds"]) + .75
    )


def evaluate_model(
    model: dict[str, object], labels: list[dict[str, object]]
) -> dict[str, object]:
    name = str(model["model"])
    rows = {str(row["clip_path"]): row for row in model["rows"]}
    policy = FIXED_DUAL_POLICIES[name]
    decisions = []
    for label in labels:
        row = rows[str(label["clip_path"])]
        matching = [
            candidate
            for candidate in row["candidates"]
            if str(candidate.get("person_name")) == str(label["person_name"])
            and overlaps(candidate, label)
        ]
        recalled = [
            candidate
            for candidate in matching
            if dual_gate_passes(candidate, policy["recall"])
        ]
        automatic = [
            candidate
            for candidate in recalled
            if dual_gate_passes(candidate, policy["auto"])
        ]
        strongest = max(
            matching,
            key=lambda item: float(item.get("track_score") or -1),
            default=None,
        )
        decisions.append(
            {
                **label,
                "raw_candidate": bool(matching),
                "recall_gate": bool(recalled),
                "auto_gate": bool(automatic),
                "strongest_candidate": strongest,
            }
        )
    confirmed = [item for item in decisions if item["review_status"] == "confirmed"]
    rejected = [item for item in decisions if item["review_status"] == "rejected"]
    return {
        "model": name,
        "metrics": {
            "confirmed_labels": len(confirmed),
            "confirmed_raw_candidates": sum(bool(item["raw_candidate"]) for item in confirmed),
            "confirmed_recall_gate": sum(bool(item["recall_gate"]) for item in confirmed),
            "confirmed_auto_gate": sum(bool(item["auto_gate"]) for item in confirmed),
            "rejected_labels": len(rejected),
            "rejected_raw_candidates": sum(bool(item["raw_candidate"]) for item in rejected),
            "rejected_recall_gate": sum(bool(item["recall_gate"]) for item in rejected),
            "rejected_auto_gate": sum(bool(item["auto_gate"]) for item in rejected),
        },
        "needs_second_review": [
            item
            for item in decisions
            if (
                item["review_status"] == "confirmed" and not item["recall_gate"]
            )
            or (item["review_status"] == "rejected" and item["auto_gate"])
        ],
        "decisions": decisions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--task-id", default=DEFAULT_TASK_ID)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    state = json.loads(args.state.read_text(encoding="utf-8"))
    task = next(item for item in state["review_tasks"] if item["task_id"] == args.task_id)
    labels = reviewed_groups(task, manifest)
    result = {
        "task_id": args.task_id,
        "task_name": task["name"],
        "reviewed_atomic_events": sum(
            event.get("review_status") != "pending"
            for event in (task.get("result") or {}).get("events", [])
        ),
        "grouped_labels": len(labels),
        "pending_atomic_events": sum(
            event.get("review_status") == "pending"
            for event in (task.get("result") or {}).get("events", [])
        ),
        "models": [evaluate_model(model, labels) for model in summary["models"]],
        "limitations": [
            "人工标签来自 SFace 候选，属于候选条件下评估，会低估 ArcFace 独有错误。",
            "当前仅 3 个排除标签，不能据此估计生产误报率。",
            "未处理事件和模型分歧项必须完成二次盲标后才能锁定自动门限。",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "reviewed_atomic_events": result["reviewed_atomic_events"],
                "grouped_labels": result["grouped_labels"],
                "pending_atomic_events": result["pending_atomic_events"],
                "models": [
                    {"model": item["model"], **item["metrics"], "needs_second_review": len(item["needs_second_review"])}
                    for item in result["models"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
