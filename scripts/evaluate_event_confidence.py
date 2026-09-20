#!/usr/bin/env python3
"""Backtest reviewer-facing confidence against saved human decisions."""
from __future__ import annotations

import argparse
import json
from statistics import mean, median
from urllib.parse import urlencode
from urllib.request import urlopen

CURRENT_ANALYSIS_PROFILE = "track_v3_continuity"

def load_tasks(api_url: str, purpose: str) -> list[dict]:
    url = f"{api_url.rstrip('/')}/api/review-tasks?{urlencode({'purpose': purpose})}"
    with urlopen(url, timeout=10) as response:  # noqa: S310 - explicit local/operator URL
        return json.load(response)


def pairwise_auc(positives: list[int], negatives: list[int]) -> float | None:
    if not positives or not negatives:
        return None
    wins = sum((positive > negative) + 0.5 * (positive == negative) for positive in positives for negative in negatives)
    return wins / (len(positives) * len(negatives))


def distribution(values: list[int]) -> dict:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "minimum": min(values),
        "median": median(values),
        "mean": round(mean(values), 2),
        "maximum": max(values),
    }


def evaluate(tasks: list[dict], thresholds: list[int]) -> dict:
    tasks = [task for task in tasks if task.get("analysis_profile") == CURRENT_ANALYSIS_PROFILE]
    labelled = [
        {"task": task.get("name", ""), **event}
        for task in tasks
        for event in (task.get("result") or {}).get("events", [])
        if event.get("review_status") in {"confirmed", "rejected"}
        and isinstance(event.get("confidence_score"), int)
    ]
    positives = [event["confidence_score"] for event in labelled if event["review_status"] == "confirmed"]
    negatives = [event["confidence_score"] for event in labelled if event["review_status"] == "rejected"]
    threshold_results = []
    for threshold in thresholds:
        selected = [event for event in labelled if event["confidence_score"] >= threshold]
        confirmed = sum(event["review_status"] == "confirmed" for event in selected)
        rejected = len(selected) - confirmed
        threshold_results.append({
            "threshold": threshold,
            "selected": len(selected),
            "precision": round(confirmed / len(selected), 4) if selected else None,
            "confirmed_coverage": round(confirmed / len(positives), 4) if positives else None,
            "false_accepts": rejected,
        })
    return {
        "analysis_profile": CURRENT_ANALYSIS_PROFILE,
        "labelled_events": len(labelled),
        "confirmed": distribution(positives),
        "rejected": distribution(negatives),
        "pairwise_ranking_auc": round(pairwise_auc(positives, negatives), 4) if negatives and positives else None,
        "thresholds": threshold_results,
        "rejected_examples": [
            {
                "task": event["task"],
                "person": event.get("person_name"),
                "start_seconds": event.get("start_seconds"),
                "confidence": event["confidence_score"],
                "dimensions": event.get("confidence_dimensions"),
            }
            for event in labelled if event["review_status"] == "rejected"
        ],
        "warning": "当前算法尚无人工标注结果。" if not labelled else "负样本少于 100 条，结果仅用于检查排序方向，不得作为概率校准或自动确认依据。" if len(negatives) < 100 else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:8770")
    parser.add_argument("--purpose", choices=("validation", "production"), default="validation")
    parser.add_argument("--thresholds", default="30,50,60,70,80,90")
    args = parser.parse_args()
    thresholds = sorted({int(value) for value in args.thresholds.split(",")})
    print(json.dumps(evaluate(load_tasks(args.api_url, args.purpose), thresholds), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
