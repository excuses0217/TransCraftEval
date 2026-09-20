#!/usr/bin/env python3
"""High-frame-rate rescan of positive-proxy and cross-film hard-negative windows.

The script extracts short local clips with the bundled ffmpeg binary, runs the
same all-library analyzer at a denser interval, and reports whether the source
identity survives increasingly strict event gates.  It never mutates task
state and can resume from already written window result files.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg

from face_watch.opencv_analyzer import AnalyzerConfig, OpenCvAnalyzer
from face_watch.review_runner import run_review

from evaluate_precision_first import EXPECTED_PEOPLE, POLICIES, media_key, passes


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / "data/media_review_state.json"
DEFAULT_OUTPUT = ROOT / "output/precision_first_validation/window_rescan"


def resolve_reference(uri: str) -> Path | None:
    if uri == "/demo/reference":
        return ROOT / "examples/reference.jpeg"
    if uri.startswith("/assets/"):
        return ROOT / "frontend_dist" / uri.lstrip("/")
    if uri.startswith("/artifacts/"):
        return ROOT / uri.lstrip("/")
    path = Path(uri)
    return path if path.is_absolute() else ROOT / path


def build_people(state: dict[str, object]) -> list[dict[str, object]]:
    people: list[dict[str, object]] = []
    for item in state.get("library_items", []):
        if item.get("category") != "person" or item.get("status") == "disabled":
            continue
        paths: list[Path] = []
        materials: list[dict[str, object]] = []
        for material in item.get("materials", []):
            if material.get("kind") != "reference_image" or material.get("status") == "disabled":
                continue
            path = resolve_reference(str(material.get("local_uri", "")))
            if path and path.is_file():
                paths.append(path)
                materials.append(material)
        if paths:
            people.append(
                {
                    "id": item["item_id"],
                    "name": item["name"],
                    "paths": paths,
                    "materials": materials,
                    "skip_invalid_references": True,
                }
            )
    return people


def select_windows(
    state: dict[str, object], negative_per_media: int, sample_positive_count: int
) -> list[dict[str, object]]:
    windows: list[dict[str, object]] = []
    full_tasks = [
        task
        for task in state.get("review_tasks", [])
        if str(task.get("name", "")).startswith("全库交叉验证")
    ]
    for task in full_tasks:
        name = str(task.get("name", ""))
        events = list((task.get("result") or {}).get("events", []))
        if name.endswith("sample"):
            candidates = sorted(
                (
                    event
                    for event in events
                    if event.get("person_name") == "朱时茂"
                ),
                key=lambda event: float(event.get("best_score") or -1),
                reverse=True,
            )
            selected: list[dict[str, object]] = []
            for event in candidates:
                center = float(event.get("evidence_seconds") or event.get("start_seconds") or 0)
                if all(abs(center - float(row["center_seconds"])) >= 8 for row in selected):
                    selected.append(
                        {
                            "kind": "known_sample_positive",
                            "media": "sample",
                            "source_person": "朱时茂",
                            "asset_path": task["asset_path"],
                            "center_seconds": center,
                            "source_score": event.get("best_score"),
                        }
                    )
                if len(selected) >= sample_positive_count:
                    break
            windows.extend(selected)
            continue
        media = media_key(name)
        if media is None:
            continue
        for person in EXPECTED_PEOPLE[media]:
            candidates = [event for event in events if event.get("person_name") == person]
            if not candidates:
                continue
            event = max(candidates, key=lambda row: float(row.get("best_score") or -1))
            windows.append(
                {
                    "kind": "cast_positive_proxy",
                    "media": media,
                    "source_person": person,
                    "asset_path": task["asset_path"],
                    "center_seconds": float(
                        event.get("evidence_seconds") or event.get("start_seconds") or 0
                    ),
                    "source_score": event.get("best_score"),
                }
            )
        negatives = sorted(
            (
                event
                for event in events
                if event.get("person_name") not in EXPECTED_PEOPLE[media]
            ),
            key=lambda event: float(event.get("best_score") or -1),
            reverse=True,
        )
        used_people: set[str] = set()
        for event in negatives:
            person = str(event.get("person_name"))
            if person in used_people:
                continue
            windows.append(
                {
                    "kind": "cross_film_hard_negative",
                    "media": media,
                    "source_person": person,
                    "asset_path": task["asset_path"],
                    "center_seconds": float(
                        event.get("evidence_seconds") or event.get("start_seconds") or 0
                    ),
                    "source_score": event.get("best_score"),
                }
            )
            used_people.add(person)
            if len(used_people) >= negative_per_media:
                break
    return windows


def extract_clip(source: Path, destination: Path, center: float, duration: float) -> float:
    start = max(0.0, center - duration / 2)
    if destination.is_file():
        return start
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(source),
        "-t",
        f"{duration:.3f}",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "18",
        "-y",
        str(destination),
    ]
    subprocess.run(command, check=True)
    return start


def summarize_window(window: dict[str, object], result: dict[str, object]) -> dict[str, object]:
    source_person = str(window["source_person"])
    events = list(result.get("events", []))
    policy_results: dict[str, dict[str, object]] = {}
    for policy in POLICIES:
        accepted = [event for event in events if passes(event, policy)]
        source_events = [
            event for event in accepted if str(event.get("person_name")) == source_person
        ]
        policy_results[policy.name] = {
            "accepted_events": len(accepted),
            "source_identity_events": len(source_events),
            "source_identity_survives": bool(source_events),
            "accepted_people": sorted(
                {str(event.get("person_name")) for event in accepted}
            ),
        }
    return {
        **window,
        "dense_events": events,
        "metrics": result.get("metrics", {}),
        "policy_results": policy_results,
    }


def aggregate(rows: list[dict[str, object]]) -> dict[str, object]:
    by_policy: dict[str, dict[str, int]] = {}
    for policy in POLICIES:
        positive = [row for row in rows if row["kind"] != "cross_film_hard_negative"]
        negative = [row for row in rows if row["kind"] == "cross_film_hard_negative"]
        by_policy[policy.name] = {
            "positive_proxy_windows": len(positive),
            "positive_source_survives": sum(
                bool(row["policy_results"][policy.name]["source_identity_survives"])
                for row in positive
            ),
            "hard_negative_windows": len(negative),
            "hard_negative_source_survives": sum(
                bool(row["policy_results"][policy.name]["source_identity_survives"])
                for row in negative
            ),
        }
    return {"windows": len(rows), "by_policy": by_policy}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--negative-per-media", type=int, default=2)
    parser.add_argument("--sample-positive-count", type=int, default=3)
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--interval", type=float, default=0.25)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    state = json.loads(args.state.read_text(encoding="utf-8"))
    people = build_people(state)
    windows = select_windows(state, args.negative_per_media, args.sample_positive_count)
    if args.limit is not None:
        windows = windows[: args.limit]
    args.output.mkdir(parents=True, exist_ok=True)
    analyzer = OpenCvAnalyzer(
        AnalyzerConfig(
            detector_model=ROOT / "models/face_detection_yunet_2023mar.onnx",
            recognizer_model=ROOT / "models/face_recognition_sface_2021dec.onnx",
            output_dir=args.output / "unused",
            detection_score_threshold=0.65,
            max_detection_side=960,
        )
    )
    rows: list[dict[str, object]] = []
    for index, window in enumerate(windows, start=1):
        item_dir = args.output / f"window-{index:03d}"
        result_path = item_dir / "result.json"
        if result_path.is_file():
            saved = json.loads(result_path.read_text(encoding="utf-8"))
            window_data = {
                key: value
                for key, value in saved.items()
                if key not in {"dense_events", "metrics", "policy_results"}
            }
            row = summarize_window(
                window_data,
                {"events": saved.get("dense_events", []), "metrics": saved.get("metrics", {})},
            )
            result_path.write_text(
                json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        else:
            clip = item_dir / "clip.mp4"
            clip_start = extract_clip(
                Path(str(window["asset_path"])), clip, float(window["center_seconds"]), args.duration
            )
            print(
                f"[{index}/{len(windows)}] {window['kind']} {window['media']} "
                f"{window['source_person']} @ {window['center_seconds']}",
                flush=True,
            )
            result = run_review(
                analyzer,
                clip,
                people,
                item_dir / "artifacts",
                lambda _: None,
                interval=args.interval,
            )
            window["clip_start_seconds"] = clip_start
            window["clip_path"] = str(clip)
            row = summarize_window(window, result)
            result_path.write_text(
                json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        rows.append(row)
    output = {
        "experiment": "high-frame-rate all-library window rescan",
        "sample_interval_seconds": args.interval,
        "clip_duration_seconds": args.duration,
        "limitations": [
            "演员表正样本窗口仍是代理标签，需人工确认框中人物身份。",
            "窗口由旧模型候选选出，不能用于估计全片漏检率。",
            "当前运行器按最佳帧保存事件；本实验主要验证连续支持门控，不等同于最终轨迹中位数实现。",
        ],
        "summary": aggregate(rows),
        "windows": rows,
    }
    (args.output / "summary.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
