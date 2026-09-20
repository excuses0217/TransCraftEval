#!/usr/bin/env python3
"""Evaluate precision-first face-event policies from completed full-library tasks.

This is deliberately a read-only proxy experiment.  A person appearing in a
film's verified cast list makes an event *eligible* to be a true positive; it
does not prove that the detected face is that person.  Cross-film events are
useful hard negatives, while final precision still requires blind track labels.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / "data/media_review_state.json"
DEFAULT_OUTPUT = ROOT / "output/precision_first_validation"

EXPECTED_PEOPLE: dict[str, frozenset[str]] = {
    "一江春水向东流": frozenset({"陶金", "上官云珠", "舒绣文"}),
    "上甘岭": frozenset({"刘玉茹"}),
    "五朵金花": frozenset({"杨丽坤", "王苏娅"}),
    "东方红": frozenset({"郭兰英", "邓玉华"}),
    "乡音": frozenset({"张伟欣", "赵越"}),
}


@dataclass(frozen=True)
class Policy:
    name: str
    min_score: float
    min_support_frames: int
    min_margin: float
    min_topk_score: float | None = None
    long_track_min_score: float | None = None
    long_track_min_support_frames: int | None = None
    long_track_min_margin: float | None = None
    long_track_min_topk_score: float | None = None


POLICIES = (
    Policy("current_baseline", 0.35, 1, 0.0),
    Policy("open_set_050", 0.50, 1, 0.03),
    Policy("track_balanced", 0.55, 3, 0.08, 0.45),
    # A long, identity-consistent track may recover lower per-frame scores
    # without relaxing the short-track confirmation gate.
    Policy("track_adaptive", 0.55, 3, 0.08, 0.45, 0.46, 8, 0.12, 0.46),
    Policy("track_precision", 0.60, 3, 0.08, 0.50),
    Policy("track_strict", 0.65, 3, 0.10, 0.55),
)


def media_key(task_name: str) -> str | None:
    return next((name for name in EXPECTED_PEOPLE if name in task_name), None)


def passes(event: dict[str, object], policy: Policy) -> bool:
    score = float(event.get("best_score") or -1)
    support = int(event.get("support_frames") or 0)
    margin_value = event.get("margin")
    margin = float(margin_value) if margin_value is not None else -1
    topk_value = event.get("topk_score")
    topk = float(topk_value) if topk_value is not None else -1
    primary = (
        score >= policy.min_score
        and support >= policy.min_support_frames
        and margin >= policy.min_margin
        and (policy.min_topk_score is None or topk >= policy.min_topk_score)
    )
    if primary:
        return True
    if policy.long_track_min_score is None:
        return False
    return (
        score >= policy.long_track_min_score
        and support >= int(policy.long_track_min_support_frames or 0)
        and margin >= float(policy.long_track_min_margin or 0)
        and (
            policy.long_track_min_topk_score is None
            or topk >= policy.long_track_min_topk_score
        )
    )


def merge_events(
    events: Iterable[dict[str, object]], gap_seconds: float
) -> list[dict[str, object]]:
    """Group adjacent same-person segments while preserving every subsegment."""
    ordered = sorted(
        events,
        key=lambda event: (
            str(event.get("person_id") or event.get("person_name") or ""),
            float(event.get("start_seconds") or 0),
        ),
    )
    groups: list[dict[str, object]] = []
    for event in ordered:
        identity = str(event.get("person_id") or event.get("person_name") or "")
        start = float(event.get("start_seconds") or 0)
        end = float(event.get("end_seconds") or start)
        segment = {
            "event_id": event.get("event_id"),
            "start_seconds": start,
            "end_seconds": end,
            "best_score": event.get("best_score"),
            "support_frames": event.get("support_frames"),
        }
        if (
            groups
            and groups[-1]["identity"] == identity
            and start - float(groups[-1]["end_seconds"]) <= gap_seconds
        ):
            group = groups[-1]
            group["end_seconds"] = max(float(group["end_seconds"]), end)
            group["segments"].append(segment)  # type: ignore[union-attr]
            group["best_score"] = max(
                float(group["best_score"]), float(event.get("best_score") or -1)
            )
            group["support_frames"] = int(group["support_frames"]) + int(
                event.get("support_frames") or 0
            )
            continue
        groups.append(
            {
                "identity": identity,
                "person_id": event.get("person_id"),
                "person_name": event.get("person_name"),
                "start_seconds": start,
                "end_seconds": end,
                "best_score": float(event.get("best_score") or -1),
                "support_frames": int(event.get("support_frames") or 0),
                "segments": [segment],
            }
        )
    return groups


def evaluate(state: dict[str, object], merge_gaps: tuple[float, ...]) -> dict[str, object]:
    tasks = [
        task
        for task in state.get("review_tasks", [])
        if str(task.get("name", "")).startswith("全库交叉验证")
        and media_key(str(task.get("name", ""))) is not None
    ]
    total_hours = sum(
        float(((task.get("result") or {}).get("metrics") or {}).get("duration_seconds") or 0)
        for task in tasks
    ) / 3600
    expected_combinations = {
        (media, person) for media, people in EXPECTED_PEOPLE.items() for person in people
    }
    policies: list[dict[str, object]] = []
    for policy in POLICIES:
        raw_events = 0
        cast_eligible = 0
        cross_film = 0
        covered: set[tuple[str, str]] = set()
        per_media: dict[str, dict[str, object]] = {}
        filtered_by_task: list[tuple[str, list[dict[str, object]]]] = []
        for task in tasks:
            media = media_key(str(task["name"]))
            assert media is not None
            filtered = [
                event
                for event in (task.get("result") or {}).get("events", [])
                if passes(event, policy)
            ]
            filtered_by_task.append((media, filtered))
            eligible = sum(
                str(event.get("person_name")) in EXPECTED_PEOPLE[media] for event in filtered
            )
            raw_events += len(filtered)
            cast_eligible += eligible
            cross_film += len(filtered) - eligible
            for event in filtered:
                person = str(event.get("person_name"))
                if person in EXPECTED_PEOPLE[media]:
                    covered.add((media, person))
            per_media[media] = {
                "events": len(filtered),
                "cast_eligible_events": eligible,
                "cross_film_events": len(filtered) - eligible,
            }
        merge_results: list[dict[str, object]] = []
        for gap in merge_gaps:
            grouped = 0
            grouped_cross = 0
            for media, events in filtered_by_task:
                groups = merge_events(events, gap)
                grouped += len(groups)
                grouped_cross += sum(
                    str(group.get("person_name")) not in EXPECTED_PEOPLE[media]
                    for group in groups
                )
            merge_results.append(
                {
                    "gap_seconds": gap,
                    "grouped_events": grouped,
                    "grouped_cross_film_events": grouped_cross,
                    "compression_ratio": round(raw_events / grouped, 3) if grouped else None,
                }
            )
        policies.append(
            {
                "policy": asdict(policy),
                "raw_events": raw_events,
                "cast_eligible_events": cast_eligible,
                "cross_film_events": cross_film,
                "cast_proxy_precision_upper_bound": (
                    round(cast_eligible / raw_events, 4) if raw_events else None
                ),
                "cross_film_events_per_video_hour": (
                    round(cross_film / total_hours, 4) if total_hours else None
                ),
                "expected_person_media_coverage": len(covered),
                "expected_person_media_total": len(expected_combinations),
                "per_media": per_media,
                "merge_results": merge_results,
            }
        )
    return {
        "experiment": "precision-first open-set proxy evaluation",
        "limitations": [
            "演员表内事件不一定命中了正确人脸，因此代理精确率只能作为上界，不能作为正式准确率。",
            "演员表外事件按硬负样本处理；客串、资料遗漏或同名错误需要人工订正。",
            "当前任务只保存事件最佳帧分数，不含逐帧分数；轨迹中位数需通过高帧率窗口复扫验证。",
        ],
        "task_count": len(tasks),
        "video_hours": round(total_hours, 3),
        "expected_person_media_combinations": len(expected_combinations),
        "policies": policies,
    }


def render_markdown(result: dict[str, object]) -> str:
    lines = [
        "# 精度优先人脸检索代理实验",
        "",
        f"覆盖 {result['task_count']} 部本地全片，合计 {result['video_hours']} 视频小时。",
        "",
        "| 策略 | 原始事件 | 演员表内候选 | 跨片候选 | 跨片候选/小时 | 应出现组合覆盖 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in result["policies"]:  # type: ignore[index]
        policy = item["policy"]
        lines.append(
            "| {name} | {raw} | {eligible} | {cross} | {density} | {coverage}/{total} |".format(
                name=policy["name"],
                raw=item["raw_events"],
                eligible=item["cast_eligible_events"],
                cross=item["cross_film_events"],
                density=item["cross_film_events_per_video_hour"],
                coverage=item["expected_person_media_coverage"],
                total=item["expected_person_media_total"],
            )
        )
    lines.extend(["", "## 连续片段归并", ""])
    for item in result["policies"]:  # type: ignore[index]
        lines.append(f"### {item['policy']['name']}")
        lines.append("")
        lines.append("| 最大间隔 | 归并后事件 | 跨片事件 | 压缩比 |")
        lines.append("| ---: | ---: | ---: | ---: |")
        for merge in item["merge_results"]:
            lines.append(
                f"| {merge['gap_seconds']} 秒 | {merge['grouped_events']} | "
                f"{merge['grouped_cross_film_events']} | {merge['compression_ratio']} |"
            )
        lines.append("")
    lines.extend(["## 解释边界", ""])
    lines.extend(f"- {limitation}" for limitation in result["limitations"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--merge-gaps", type=float, nargs="+", default=(1.5, 3.0, 5.0))
    args = parser.parse_args()
    state = json.loads(args.state.read_text(encoding="utf-8"))
    result = evaluate(state, tuple(args.merge_gaps))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output / "report.md").write_text(render_markdown(result), encoding="utf-8")
    print(render_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
