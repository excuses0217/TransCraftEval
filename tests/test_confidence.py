from face_watch.confidence import attach_event_confidence, event_confidence


def test_strong_consistent_track_gets_high_explainable_confidence():
    result = event_confidence({
        "track_score": 0.58,
        "topk_score": 0.53,
        "margin": 0.14,
        "quality": 0.76,
        "reference_count": 4,
        "independent_support": 5,
        "vote_ratio": 1.0,
        "early_late_consistent": True,
    })

    assert result["confidence_score"] >= 80
    assert result["confidence_level"] == "high"
    assert result["confidence_is_probability"] is False
    assert any("时间点" in factor for factor in result["confidence_factors"])


def test_weak_or_conflicting_evidence_is_not_presented_as_high_confidence():
    result = event_confidence({
        "best_score": 0.48,
        "track_score": 0.41,
        "topk_score": 0.39,
        "margin": 0.035,
        "quality": 0.36,
        "reference_count": 3,
        "independent_support": 1,
        "vote_ratio": 0.5,
        "early_late_consistent": False,
        "ambiguous": True,
    })

    assert result["confidence_level"] == "low"
    assert result["confidence_score"] < 60
    assert "系统发现身份歧义" in result["confidence_cautions"]


def test_confidence_can_be_attached_to_api_event_shape():
    event = {"best_score": 0.55, "support_frames": 3, "margin": 0.1, "reference_count": 2}

    returned = attach_event_confidence(event)

    assert returned is event
    assert event["confidence_kind"] == "evidence_strength_v2"
    assert isinstance(event["confidence_score"], int)


def test_single_reference_never_claims_high_confidence():
    result = event_confidence({
        "track_score": 0.62,
        "topk_score": 0.60,
        "margin": 0.18,
        "quality": 0.9,
        "reference_count": 1,
        "independent_support": 8,
        "vote_ratio": 1.0,
        "early_late_consistent": True,
    })

    assert result["confidence_score"] <= 79
    assert result["confidence_level"] == "medium"
    assert any("1 张参考照片" in caution for caution in result["confidence_cautions"])


def test_environment_and_temporal_failures_reduce_confidence():
    strong = {
        "track_score": 0.58,
        "topk_score": 0.52,
        "score_p25": 0.53,
        "margin": 0.14,
        "quality": 0.8,
        "reference_count": 4,
        "independent_support": 5,
        "vote_ratio": 1.0,
        "track_cohesion": 0.9,
        "early_late_consistent": True,
    }
    strong_result = event_confidence(strong)
    poor_environment = event_confidence({
        **strong,
        "environment_signals": {
            "sharpness": 0.15,
            "face_size": 0.2,
            "detector_confidence": 0.5,
            "exposure": 0.2,
            "frontalness": 0.25,
        },
    })
    unstable_track = event_confidence({
        **strong,
        "independent_support": 1,
        "vote_ratio": 0.5,
        "track_cohesion": 0.5,
        "score_p25": 0.38,
        "early_late_consistent": False,
    })

    assert strong_result["confidence_score"] > poor_environment["confidence_score"]
    assert strong_result["confidence_score"] > unstable_track["confidence_score"]
    assert poor_environment["confidence_dimensions"]["environment_quality"] < 30
    assert unstable_track["confidence_dimensions"]["temporal_consistency"] < 50
