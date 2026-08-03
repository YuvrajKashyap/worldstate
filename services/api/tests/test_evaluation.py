from __future__ import annotations

from pathlib import Path

import pytest

from worldstate_api.evaluation import (
    binary_metrics,
    evaluate_manifest,
    expected_calibration_error,
    intersection_over_union,
    latency_summary,
    numeric_summary,
    provenance,
    tracking_metrics,
    write_parquet_if_available,
)


def test_metric_primitives_are_deterministic() -> None:
    metrics = binary_metrics(true_positives=8, false_positives=2, false_negatives=2)
    assert metrics.precision == pytest.approx(0.8)
    assert metrics.recall == pytest.approx(0.8)
    assert metrics.f1 == pytest.approx(0.8)
    assert intersection_over_union((0, 0, 2, 2), (1, 1, 3, 3)) == pytest.approx(1 / 7)
    assert latency_summary([10, 20, 30]) == {
        "count": 3.0,
        "mean_ms": 20.0,
        "p50_ms": 20.0,
        "p95_ms": 29.0,
    }


def test_metric_validation_catches_invalid_values() -> None:
    with pytest.raises(ValueError, match="negative"):
        binary_metrics(true_positives=-1, false_positives=0, false_negatives=0)
    with pytest.raises(ValueError, match="equal length"):
        expected_calibration_error([0.5], [])
    with pytest.raises(ValueError, match="bins"):
        expected_calibration_error([], [], bins=0)
    with pytest.raises(ValueError, match="between"):
        expected_calibration_error([2.0], [True])
    with pytest.raises(ValueError, match="negative"):
        latency_summary([-1])


def test_manifest_evaluation_and_provenance() -> None:
    payload = {
        "schema_version": 1,
        "event_counts": {"true_positives": 9, "false_positives": 1, "false_negatives": 1},
        "confidences": [0.9, 0.1],
        "outcomes": [True, False],
        "latency_ms": [40, 60],
    }

    report = evaluate_manifest(payload)
    evidence = provenance(config={"seed": 7}, dataset_hash="abc")

    assert report["event_f1"] == pytest.approx(0.9)
    assert report["calibration_ece"] == pytest.approx(0.1)
    assert evidence["dataset_hash"] == "abc"
    assert len(str(evidence["config_hash"])) == 64


@pytest.mark.parametrize(
    "payload,message",
    [
        ({}, "schema_version"),
        ({"schema_version": 1}, "event_counts"),
        ({"schema_version": 1, "event_counts": {}, "confidences": {}}, "confidences"),
        (
            {"schema_version": 1, "event_counts": {"true_positives": "one"}},
            "integer",
        ),
    ],
)
def test_manifest_validation(payload: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        evaluate_manifest(payload)


def test_parquet_writer_is_optional(tmp_path: Path) -> None:
    result = write_parquet_if_available([{"value": 1}], tmp_path / "result.parquet")
    assert result in {True, False}


def test_tracking_and_distribution_metrics_cover_research_outputs() -> None:
    tracking = tracking_metrics(
        {
            "detection_tp": 9,
            "detection_fp": 1,
            "detection_fn": 1,
            "association_tp": 8,
            "association_fp": 2,
            "association_fn": 2,
            "idtp": 8,
            "idfp": 1,
            "idfn": 1,
            "id_switches": 2,
            "track_fragmentations": 3,
        }
    )
    assert tracking["idf1"] == pytest.approx(8 / 9)
    assert 0 < tracking["hota"] < 1
    assert numeric_summary([1, 2, 3])["p95"] == pytest.approx(2.9)
    with pytest.raises(ValueError, match="finite"):
        numeric_summary([float("nan")])


def test_manifest_supports_tracking_geometry_and_system_metrics() -> None:
    payload = {
        "schema_version": 1,
        "event_counts": {"true_positives": 1, "false_positives": 0, "false_negatives": 0},
        "tracking_counts": {"idtp": 1},
        "confidences": [0.9],
        "outcomes": [True],
        "latency_ms": [10],
        "mask_iou": [0.8, 0.9],
        "last_seen_timestamp_error_seconds": [0.2],
        "scale_error_fraction": [0.05],
        "vram_peak_bytes": [7_000_000_000],
        "detection_map": 0.75,
    }
    report = evaluate_manifest(payload)
    assert report["tracking"]["idf1"] == 1.0  # type: ignore[index]
    assert report["mask_iou"]["mean"] == pytest.approx(0.85)  # type: ignore[index]
    assert report["detection_map"] == 0.75

    payload["detection_map"] = 2
    with pytest.raises(ValueError, match="detection_map"):
        evaluate_manifest(payload)
