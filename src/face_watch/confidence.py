"""Reviewer-facing confidence derived from track-level evidence.

This is deliberately an evidence-strength score, not a calibrated identity
probability.  Keeping the calculation here makes the meaning explicit and
allows a future labelled calibration model to replace it without changing the
review API.
"""
from __future__ import annotations

from typing import Any


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalise(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return _clamp((value - low) / (high - low))


def event_confidence(event: dict[str, Any]) -> dict[str, Any]:
    """Return an explainable 0-100 evidence confidence for one review event.

    The ranges are conservative engineering priors for SFace cosine scores.
    They rank review evidence consistently but must not be interpreted as a
    statistical probability until a labelled calibration set is available.
    """
    best = float(event.get("best_score") or 0.0)
    track = float(event.get("track_score") or event.get("score_median") or best)
    topk = float(event.get("topk_score") or track)
    margin = float(event.get("margin") or 0.0)
    raw_quality = event.get("quality")
    quality = float(raw_quality) if raw_quality is not None else 0.5
    reference_count = int(event.get("reference_count") or 0)
    support = int(event.get("independent_support") or event.get("support_frames") or 0)
    vote_ratio = float(event.get("vote_ratio") or (1.0 if support >= 3 else support / 3.0))
    consistent = bool(event.get("early_late_consistent", support >= 3))

    match_strength = _normalise(track, 0.35, 0.60)
    reference_coverage = 1.0 if reference_count >= 3 else 0.75 if reference_count == 2 else 0.45 if reference_count == 1 else 0.35
    reference_agreement = _normalise(topk, 0.35, 0.55)
    identity_separation = _normalise(margin, 0.03, 0.12)
    score_stability = _normalise(float(event.get("score_p25") or track), 0.35, 0.55)
    track_cohesion = _normalise(float(event.get("track_cohesion") or 0.65), 0.45, 0.85)
    temporal_support = (
        0.30 * _clamp(vote_ratio)
        + 0.20 * _clamp(support / 4.0)
        + 0.18 * (1.0 if consistent else 0.0)
        + 0.17 * score_stability
        + 0.15 * track_cohesion
    )
    environment_signals = event.get("environment_signals")
    environment_available = raw_quality is not None or bool(environment_signals)
    if isinstance(environment_signals, dict) and environment_signals:
        image_quality = sum(
            float(environment_signals.get(key, quality)) * weight
            for key, weight in {
                "sharpness": 0.24,
                "face_size": 0.22,
                "detector_confidence": 0.18,
                "exposure": 0.18,
                "frontalness": 0.18,
            }.items()
        )
        image_quality = _clamp(image_quality)
    else:
        image_quality = _normalise(quality, 0.30, 0.80) if environment_available else 0.5

    model_evidence = 0.45 * match_strength + 0.25 * reference_agreement + 0.30 * identity_separation

    value = 100.0 * (
        0.38 * model_evidence
        + 0.30 * temporal_support
        + 0.17 * image_quality
        + 0.15 * reference_coverage
    )
    if bool(event.get("ambiguous")):
        value -= 10.0
    if not consistent:
        value -= 8.0
    score = int(round(max(0.0, min(100.0, value))))
    if reference_count <= 0:
        score = min(score, 69)
    elif reference_count == 1:
        score = min(score, 79)

    high_gate = reference_count >= 2 and support >= 3 and margin >= 0.08 and consistent and not bool(event.get("ambiguous"))
    level = "high" if score >= 80 and high_gate else "medium" if score >= 60 else "low"

    factors: list[str] = []
    cautions: list[str] = []
    if bool(event.get("ambiguous")):
        cautions.append("系统发现身份歧义")
    if not environment_available:
        cautions.append("历史结果缺少完整画面环境指标")
    if reference_count <= 0:
        cautions.append("参考照片覆盖信息不足")
    elif reference_count == 1:
        cautions.append("仅有 1 张参考照片，覆盖有限")
    if support >= 4:
        factors.append(f"多个时间点持续支持（{support} 个）")
    elif support >= 2:
        factors.append(f"有 {support} 个时间点支持")
    else:
        cautions.append("有效支持画面较少")
    if consistent:
        factors.append("片段前后判断一致")
    else:
        cautions.append("片段内判断不够稳定")
    if margin >= 0.10:
        factors.append("与其他候选区分明显")
    elif margin < 0.06:
        cautions.append("与其他候选人物较接近")
    if environment_available and quality >= 0.70:
        factors.append("画面环境适合人脸判断")
    elif environment_available and quality < 0.45:
        cautions.append("清晰度、角度或光照可能影响判断")
    return {
        "confidence_score": score,
        "confidence_level": level,
        "confidence_factors": factors[:3],
        "confidence_cautions": cautions[:3],
        "confidence_kind": "evidence_strength_v2",
        "confidence_is_probability": False,
        "confidence_dimensions": {
            "model_evidence": int(round(model_evidence * 100)),
            "temporal_consistency": int(round(temporal_support * 100)),
            "environment_quality": int(round(image_quality * 100)) if environment_available else None,
            "reference_coverage": int(round(reference_coverage * 100)),
        },
    }


def attach_event_confidence(event: dict[str, Any]) -> dict[str, Any]:
    event.update(event_confidence(event))
    return event
