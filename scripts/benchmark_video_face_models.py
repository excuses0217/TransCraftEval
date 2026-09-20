#!/usr/bin/env python3
"""Compare face encoders on the same local video tracks.

This experiment is intentionally read-only with respect to product state.  It
reuses the 23 dense validation windows, keeps YuNet detection/alignment and the
track assembler fixed, and changes only the recognition embedding model.

The labels are proxies selected from historical candidates.  Results estimate
how much review work a policy could remove; they are not formal precision or
recall claims until the windows have independent blind labels.
"""
from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from face_watch.arcface_analyzer import ArcFaceAnalyzer
from face_watch.opencv_analyzer import AnalyzerConfig, OpenCvAnalyzer
from face_watch.video_track_runner import TrackPolicy, run_track_review
from rescan_precision_windows import build_people


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WINDOWS = ROOT / "output/precision_first_validation/window_rescan/summary.json"
DEFAULT_OUTPUT = ROOT / "output/video_face_model_ab"

# These are deliberately conservative absolute floors, not learned final
# thresholds.  They prevent a stable but low-similarity identity from being
# promoted merely because it wins every frame in an open-set search.
MODEL_FLOORS = {
    "sface": {
        "recall_track": .30,
        "recall_p25": .18,
        "auto_track": .44,
        "auto_p25": .28,
    },
    "arcface": {
        "recall_track": .30,
        "recall_p25": .18,
        "auto_track": .40,
        "auto_p25": .30,
    },
}


@dataclass(frozen=True)
class Gate:
    min_track_score: float
    min_score_p25: float
    min_margin: float
    min_vote_ratio: float
    min_track_frames: int
    require_early_late: bool


@dataclass(frozen=True)
class DualGate:
    short: Gate
    sustained: Gate


FIXED_DUAL_POLICIES = {
    "sface": {
        "recall": DualGate(
            short=Gate(.55, .35, .12, .75, 3, False),
            sustained=Gate(.30, .18, .05, .50, 6, False),
        ),
        "auto": DualGate(
            short=Gate(.58, .40, .15, .90, 3, True),
            sustained=Gate(.44, .28, .10, .75, 6, True),
        ),
    },
    "arcface": {
        "recall": DualGate(
            short=Gate(.50, .35, .15, .75, 3, False),
            sustained=Gate(.30, .18, .08, .65, 6, False),
        ),
        "auto": DualGate(
            short=Gate(.52, .40, .20, .90, 3, True),
            sustained=Gate(.40, .30, .15, .90, 6, True),
        ),
    },
}


def make_analyzer(name: str, output: Path):
    config = AnalyzerConfig(
        detector_model=ROOT / "models/face_detection_yunet_2023mar.onnx",
        recognizer_model=ROOT / "models/face_recognition_sface_2021dec.onnx",
        output_dir=output,
        detection_score_threshold=.65,
        max_detection_side=960,
    )
    if name == "sface":
        return OpenCvAnalyzer(config)
    if name == "arcface":
        return ArcFaceAnalyzer(config, ROOT / "models/insightface/w600k_r50.onnx")
    raise ValueError(f"unknown model: {name}")


def gate_passes(candidate: dict[str, object], gate: Gate) -> bool:
    return (
        float(candidate.get("track_score") or -1) >= gate.min_track_score
        and float(candidate.get("score_p25") or -1) >= gate.min_score_p25
        and float(candidate.get("margin") or -1) >= gate.min_margin
        and float(candidate.get("vote_ratio") or 0) >= gate.min_vote_ratio
        and int(candidate.get("track_frames") or 0) >= gate.min_track_frames
        and (
            not gate.require_early_late
            or bool(candidate.get("early_late_consistent"))
        )
    )


def dual_gate_passes(candidate: dict[str, object], gate: DualGate) -> bool:
    return gate_passes(candidate, gate.short) or gate_passes(candidate, gate.sustained)


def quantile_grid(values: Iterable[float], count: int = 9) -> tuple[float, ...]:
    array = np.asarray(list(values), dtype=np.float32)
    if not array.size:
        return (-1.0,)
    quantiles = np.linspace(0, 1, count)
    result = {-1.0}
    result.update(round(float(value), 4) for value in np.quantile(array, quantiles))
    return tuple(sorted(result))


def gate_space(rows: list[dict[str, object]], extra_scores: Iterable[float] = ()) -> Iterable[Gate]:
    candidates = [
        candidate
        for row in rows
        for candidate in row.get("candidates", [])
    ]
    track_scores = set(quantile_grid(float(row.get("track_score") or -1) for row in candidates))
    p25_scores = set(quantile_grid(float(row.get("score_p25") or -1) for row in candidates))
    track_scores.update(extra_scores)
    p25_scores.update(extra_scores)
    margins = (0.0, .03, .05, .08, .10, .15, .20)
    votes = (0.0, .50, .65, .75, .90, 1.0)
    frames = (1, 3, 6, 10)
    for values in itertools.product(
        track_scores, p25_scores, margins, votes, frames, (False, True)
    ):
        yield Gate(*values)


def measure(rows: list[dict[str, object]], gate: Gate) -> dict[str, int]:
    positive = [row for row in rows if row["kind"] != "cross_film_hard_negative"]
    negative = [row for row in rows if row["kind"] == "cross_film_hard_negative"]

    def source_survives(row: dict[str, object]) -> bool:
        return any(
            str(candidate.get("person_name")) == str(row["source_person"])
            and gate_passes(candidate, gate)
            for candidate in row.get("candidates", [])
        )

    passed_tracks = sum(
        gate_passes(candidate, gate)
        for row in rows
        for candidate in row.get("candidates", [])
    )
    return {
        "positive_windows": len(positive),
        "positive_source_survives": sum(source_survives(row) for row in positive),
        "hard_negative_windows": len(negative),
        "hard_negative_source_survives": sum(source_survives(row) for row in negative),
        "passed_tracks": passed_tracks,
    }


def select_gates(name: str, rows: list[dict[str, object]]) -> tuple[tuple[Gate, dict[str, int]], tuple[Gate, dict[str, int]]]:
    floors = MODEL_FLOORS[name]
    scored = [
        (gate, measure(rows, gate))
        for gate in gate_space(rows, floors.values())
    ]
    recall_candidates = [
        item
        for item in scored
        if item[0].min_track_score >= floors["recall_track"]
        and item[0].min_score_p25 >= floors["recall_p25"]
        and item[0].min_vote_ratio >= .50
        and item[0].min_track_frames >= 3
    ]
    recall = max(
        recall_candidates,
        key=lambda item: (
            item[1]["positive_source_survives"],
            -item[1]["hard_negative_source_survives"],
            -item[1]["passed_tracks"],
        ),
    )
    zero_negative = [
        item
        for item in scored
        if item[1]["hard_negative_source_survives"] == 0
        and item[0].min_track_score >= floors["auto_track"]
        and item[0].min_score_p25 >= floors["auto_p25"]
        and item[0].min_vote_ratio >= .75
        and item[0].min_track_frames >= 3
        and item[0].require_early_late
    ]
    auto = max(
        zero_negative,
        key=lambda item: (
            item[1]["positive_source_survives"],
            -item[1]["passed_tracks"],
            item[0].min_vote_ratio,
            item[0].min_track_frames,
        ),
    )
    return recall, auto


def source_separation(rows: list[dict[str, object]]) -> dict[str, object]:
    positive: list[dict[str, object]] = []
    negative: list[dict[str, object]] = []
    for row in rows:
        source = [
            candidate
            for candidate in row.get("candidates", [])
            if str(candidate.get("person_name")) == str(row["source_person"])
        ]
        if not source:
            continue
        best = max(source, key=lambda item: float(item.get("track_score") or -1))
        target = negative if row["kind"] == "cross_film_hard_negative" else positive
        target.append(best)

    def range_for(field: str) -> dict[str, float | None]:
        minimum_positive = min(
            (float(item[field]) for item in positive), default=None
        )
        maximum_negative = max(
            (float(item[field]) for item in negative), default=None
        )
        return {
            "minimum_positive": round(minimum_positive, 5) if minimum_positive is not None else None,
            "maximum_hard_negative": round(maximum_negative, 5) if maximum_negative is not None else None,
            "separation_gap": (
                round(minimum_positive - maximum_negative, 5)
                if minimum_positive is not None and maximum_negative is not None
                else None
            ),
        }

    return {
        "track_score": range_for("track_score"),
        "score_p25": range_for("score_p25"),
        "margin": range_for("margin"),
    }


def workload(
    rows: list[dict[str, object]], recall_gate: Gate, auto_gate: Gate
) -> dict[str, object]:
    raw_tracks = sum(len(row.get("candidates", [])) for row in rows)
    recalled = []
    automatic = []
    for row in rows:
        for candidate in row.get("candidates", []):
            if not gate_passes(candidate, recall_gate):
                continue
            key = (row["window_index"], str(candidate.get("track_id")))
            recalled.append(key)
            if gate_passes(candidate, auto_gate):
                automatic.append(key)
    automatic_keys = set(automatic)
    review = [key for key in recalled if key not in automatic_keys]
    return {
        "raw_tracks": raw_tracks,
        "filtered_before_review": raw_tracks - len(recalled),
        "recall_gate_tracks": len(recalled),
        "machine_auto_candidates": len(automatic_keys),
        "human_review_tracks": len(review),
        "estimated_review_reduction": (
            round(len(automatic_keys) / len(recalled), 4) if recalled else None
        ),
    }


def evaluate_dual_policy(name: str, rows: list[dict[str, object]]) -> dict[str, object]:
    policy = FIXED_DUAL_POLICIES[name]
    recall_gate = policy["recall"]
    auto_gate = policy["auto"]
    counts = {
        "positive_windows": 0,
        "positive_source_recalled": 0,
        "positive_source_auto": 0,
        "hard_negative_windows": 0,
        "hard_negative_source_recalled": 0,
        "hard_negative_source_auto": 0,
        "raw_tracks": 0,
        "recalled_tracks": 0,
        "machine_auto_candidates": 0,
        "human_review_tracks": 0,
    }
    for row in rows:
        candidates = list(row.get("candidates", []))
        recalled = [
            candidate
            for candidate in candidates
            if dual_gate_passes(candidate, recall_gate)
        ]
        automatic = [
            candidate
            for candidate in recalled
            if dual_gate_passes(candidate, auto_gate)
        ]
        source = str(row["source_person"])
        source_recalled = any(str(item.get("person_name")) == source for item in recalled)
        source_auto = any(str(item.get("person_name")) == source for item in automatic)
        if row["kind"] == "cross_film_hard_negative":
            counts["hard_negative_windows"] += 1
            counts["hard_negative_source_recalled"] += source_recalled
            counts["hard_negative_source_auto"] += source_auto
        else:
            counts["positive_windows"] += 1
            counts["positive_source_recalled"] += source_recalled
            counts["positive_source_auto"] += source_auto
        counts["raw_tracks"] += len(candidates)
        counts["recalled_tracks"] += len(recalled)
        counts["machine_auto_candidates"] += len(automatic)
        counts["human_review_tracks"] += len(recalled) - len(automatic)
    counts["estimated_review_reduction"] = (
        round(counts["machine_auto_candidates"] / counts["recalled_tracks"], 4)
        if counts["recalled_tracks"]
        else None
    )
    return {
        "policy": {
            "recall": asdict(recall_gate),
            "auto": asdict(auto_gate),
        },
        "metrics": counts,
    }


def cross_validate(name: str, rows: list[dict[str, object]]) -> dict[str, object]:
    """Leave one title out so reported workload is not fitted and scored together."""
    aggregate_recall = {
        "positive_windows": 0,
        "positive_source_survives": 0,
        "hard_negative_windows": 0,
        "hard_negative_source_survives": 0,
        "passed_tracks": 0,
    }
    aggregate_auto = dict(aggregate_recall)
    aggregate_workload = {
        "raw_tracks": 0,
        "filtered_before_review": 0,
        "recall_gate_tracks": 0,
        "machine_auto_candidates": 0,
        "human_review_tracks": 0,
    }
    folds = []
    for media in sorted({str(row["media"]) for row in rows}):
        training = [row for row in rows if str(row["media"]) != media]
        held_out = [row for row in rows if str(row["media"]) == media]
        recall, auto = select_gates(name, training)
        recall_metrics = measure(held_out, recall[0])
        auto_metrics = measure(held_out, auto[0])
        held_out_workload = workload(held_out, recall[0], auto[0])
        for key in aggregate_recall:
            aggregate_recall[key] += recall_metrics[key]
            aggregate_auto[key] += auto_metrics[key]
        for key in aggregate_workload:
            aggregate_workload[key] += int(held_out_workload[key])
        folds.append(
            {
                "held_out_media": media,
                "recall_gate": asdict(recall[0]),
                "auto_gate": asdict(auto[0]),
                "recall_proxy_metrics": recall_metrics,
                "auto_proxy_metrics": auto_metrics,
                "workload": held_out_workload,
            }
        )
    recalled = aggregate_workload["recall_gate_tracks"]
    automatic = aggregate_workload["machine_auto_candidates"]
    aggregate_workload["estimated_review_reduction"] = (
        round(automatic / recalled, 4) if recalled else None
    )
    return {
        "method": "leave-one-media-out",
        "fold_count": len(folds),
        "recall_proxy_metrics": aggregate_recall,
        "auto_proxy_metrics": aggregate_auto,
        "workload": aggregate_workload,
        "folds": folds,
    }


def benchmark_model(
    name: str,
    windows: list[dict[str, object]],
    people: list[dict[str, object]],
    output: Path,
    interval: float,
    force: bool,
) -> dict[str, object]:
    model_output = output / name
    model_output.mkdir(parents=True, exist_ok=True)
    analyzer = make_analyzer(name, model_output / "analyzer")
    rows: list[dict[str, object]] = []
    diagnostic_policy = TrackPolicy(
        candidate_threshold=-1,
        short_min_score=2,
        long_min_score=2,
    )
    for index, window in enumerate(windows, start=1):
        result_path = model_output / f"window-{index:03d}.json"
        if result_path.is_file() and not force:
            row = json.loads(result_path.read_text(encoding="utf-8"))
        else:
            print(
                f"[{name} {index}/{len(windows)}] {window['media']} / "
                f"{window['source_person']}",
                flush=True,
            )
            result = run_track_review(
                analyzer,
                Path(str(window["clip_path"])),
                people,
                model_output / "artifacts",
                lambda _: None,
                interval=interval,
                policy=diagnostic_policy,
                include_diagnostics=True,
            )
            row = {
                "window_index": index,
                "kind": window["kind"],
                "media": window["media"],
                "source_person": window["source_person"],
                "clip_path": window["clip_path"],
                "metrics": result["metrics"],
                "candidates": result["track_candidates"],
            }
            result_path.write_text(
                json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        rows.append(row)

    recall, auto = select_gates(name, rows)
    validation = cross_validate(name, rows)
    elapsed = sum(float(row["metrics"].get("elapsed_seconds") or 0) for row in rows)
    video_seconds = sum(float(row["metrics"].get("duration_seconds") or 0) for row in rows)
    return {
        "model": name,
        "windows": len(rows),
        "runtime": {
            "video_seconds": round(video_seconds, 3),
            "elapsed_seconds": round(elapsed, 3),
            "realtime_factor": round(elapsed / video_seconds, 4) if video_seconds else None,
        },
        "source_separation": source_separation(rows),
        "fixed_dual_policy": evaluate_dual_policy(name, rows),
        "development_fit": {
            "recall_gate": {
                "gate": asdict(recall[0]),
                "proxy_metrics": recall[1],
            },
            "auto_gate": {
                "gate": asdict(auto[0]),
                "proxy_metrics": auto[1],
            },
            "workload": workload(rows, recall[0], auto[0]),
        },
        "cross_validation": validation,
        "rows": rows,
    }


def render_markdown(result: dict[str, object]) -> str:
    lines = [
        "# 视频人脸模型 A/B 与人工工作量代理实验",
        "",
        "本实验固定 YuNet 检测、五点对齐、轨迹组装和 0.25 秒采样，只替换人脸编码器。",
        "",
        "## 双入口候选策略",
        "",
        "短轨迹只有在单帧与身份分差都很强时自动通过；长轨迹允许较低单帧分数，但要求持续投票、低四分位和前后段一致。",
        "",
        "| 模型 | 正样本代理保留（召回门） | 强负样本穿透（召回门） | 自动候选正样本 | 自动候选强负样本 | 进入人工复核轨迹 | 代理复核降幅 | 实时系数 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in result["models"]:
        metrics = item["fixed_dual_policy"]["metrics"]
        reduction = metrics["estimated_review_reduction"]
        lines.append(
            f"| {item['model']} | {metrics['positive_source_recalled']}/{metrics['positive_windows']} | "
            f"{metrics['hard_negative_source_recalled']}/{metrics['hard_negative_windows']} | "
            f"{metrics['positive_source_auto']}/{metrics['positive_windows']} | "
            f"{metrics['hard_negative_source_auto']}/{metrics['hard_negative_windows']} | "
            f"{metrics['human_review_tracks']} | "
            f"{f'{reduction:.1%}' if reduction is not None else '-'} | "
            f"{item['runtime']['realtime_factor']} |"
        )
    lines.extend(
        [
            "",
            "## 按影片留一检查",
            "",
            "该检查只用其他影片自动选择单入口门限，专门暴露跨影片泛化和短片段漏检问题。",
            "",
            "| 模型 | 正样本代理保留 | 自动候选正样本 | 自动候选强负样本 | 仍需人工轨迹 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in result["models"]:
        recall = item["cross_validation"]["recall_proxy_metrics"]
        auto = item["cross_validation"]["auto_proxy_metrics"]
        work = item["cross_validation"]["workload"]
        lines.append(
            f"| {item['model']} | {recall['positive_source_survives']}/{recall['positive_windows']} | "
            f"{auto['positive_source_survives']}/{auto['positive_windows']} | "
            f"{auto['hard_negative_source_survives']}/{auto['hard_negative_windows']} | "
            f"{work['human_review_tracks']} |"
        )
    lines.extend(["", "## 正负样本分离度", ""])
    lines.extend(
        [
            "| 模型 | 轨迹分数间隔 | 低四分位间隔 | Top-1/Top-2 分差间隔 |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for item in result["models"]:
        separation = item["source_separation"]
        lines.append(
            f"| {item['model']} | {separation['track_score']['separation_gap']} | "
            f"{separation['score_p25']['separation_gap']} | "
            f"{separation['margin']['separation_gap']} |"
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- 正样本来自演员表与历史候选交集，是代理标签，不证明框中人脸身份。",
            "- 强负样本只验证指定跨片身份是否被错误召回，不覆盖库中所有潜在误报。",
            "- 门限是在同一小样本上搜索得到，数值只能用于筛选路线；上线阈值必须在独立盲标集上锁定。",
            "- 表格采用按影片留一验证：每轮只用其他影片选择门限，再在未参与选门限的影片上计数。",
            "- `machine_auto_candidates` 表示可进入自动确认候选区，独立盲测通过前仍不能直接替代人工结论。",
            "- InsightFace 预训练权重用于本地技术验证；商业化前需确认或替换为许可明确的权重。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", type=Path, default=DEFAULT_WINDOWS)
    parser.add_argument("--state", type=Path, default=ROOT / "data/media_review_state.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--models", nargs="+", choices=("sface", "arcface"), default=("sface", "arcface"))
    parser.add_argument("--interval", type=float, default=.25)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source = json.loads(args.windows.read_text(encoding="utf-8"))
    windows = list(source["windows"])
    if args.limit is not None:
        windows = windows[: args.limit]
    state = json.loads(args.state.read_text(encoding="utf-8"))
    people = build_people(state)
    args.output.mkdir(parents=True, exist_ok=True)

    models = [
        benchmark_model(name, windows, people, args.output, args.interval, args.force)
        for name in args.models
    ]
    report = {
        "experiment": "fixed-track face encoder A/B and review workload proxy",
        "sample_interval_seconds": args.interval,
        "model_results": [
            {key: value for key, value in item.items() if key != "rows"}
            for item in models
        ],
        "models": models,
    }
    (args.output / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown = render_markdown(report)
    (args.output / "report.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
