# pyright: basic, reportMissingImports=false, reportMissingTypeStubs=false
"""Deterministic evaluation primitives and experiment provenance."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import statistics
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast


@dataclass(frozen=True, slots=True)
class BinaryMetrics:
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int


def binary_metrics(
    *, true_positives: int, false_positives: int, false_negatives: int
) -> BinaryMetrics:
    if min(true_positives, false_positives, false_negatives) < 0:
        raise ValueError("metric counts cannot be negative")
    precision_denominator = true_positives + false_positives
    recall_denominator = true_positives + false_negatives
    precision = true_positives / precision_denominator if precision_denominator else 0.0
    recall = true_positives / recall_denominator if recall_denominator else 0.0
    denominator = precision + recall
    f1 = 2.0 * precision * recall / denominator if denominator else 0.0
    return BinaryMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
    )


def intersection_over_union(
    predicted: tuple[float, float, float, float],
    expected: tuple[float, float, float, float],
) -> float:
    px1, py1, px2, py2 = predicted
    ex1, ey1, ex2, ey2 = expected
    intersection = max(0.0, min(px2, ex2) - max(px1, ex1)) * max(
        0.0,
        min(py2, ey2) - max(py1, ey1),
    )
    predicted_area = max(0.0, px2 - px1) * max(0.0, py2 - py1)
    expected_area = max(0.0, ex2 - ex1) * max(0.0, ey2 - ey1)
    union = predicted_area + expected_area - intersection
    return intersection / union if union > 0.0 else 0.0


def expected_calibration_error(
    confidences: list[float],
    outcomes: list[bool],
    *,
    bins: int = 10,
) -> float:
    if len(confidences) != len(outcomes):
        raise ValueError("confidence and outcome lists must have equal length")
    if bins <= 0:
        raise ValueError("bins must be positive")
    if not confidences:
        return 0.0
    if any(not 0.0 <= value <= 1.0 for value in confidences):
        raise ValueError("confidences must be between 0 and 1")

    error = 0.0
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        members = [
            item
            for item, confidence in enumerate(confidences)
            if lower <= confidence < upper or (index == bins - 1 and confidence == 1.0)
        ]
        if not members:
            continue
        average_confidence = statistics.fmean(confidences[item] for item in members)
        accuracy = statistics.fmean(float(outcomes[item]) for item in members)
        error += len(members) / len(confidences) * abs(accuracy - average_confidence)
    return error


def latency_summary(samples_ms: list[float]) -> dict[str, float]:
    if not samples_ms:
        return {"count": 0.0, "mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0}
    if any(value < 0.0 for value in samples_ms):
        raise ValueError("latency samples cannot be negative")
    ordered = sorted(samples_ms)

    def percentile(fraction: float) -> float:
        position = (len(ordered) - 1) * fraction
        lower = int(position)
        upper = min(len(ordered) - 1, lower + 1)
        weight = position - lower
        return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

    return {
        "count": float(len(samples_ms)),
        "mean_ms": statistics.fmean(samples_ms),
        "p50_ms": percentile(0.50),
        "p95_ms": percentile(0.95),
    }


def numeric_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0.0, "mean": 0.0, "p50": 0.0, "p95": 0.0}
    if any(not math.isfinite(value) for value in values):
        raise ValueError("numeric metric samples must be finite")
    ordered = sorted(values)

    def percentile(fraction: float) -> float:
        position = (len(ordered) - 1) * fraction
        lower = int(position)
        upper = min(len(ordered) - 1, lower + 1)
        weight = position - lower
        return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

    return {
        "count": float(len(values)),
        "mean": statistics.fmean(values),
        "p50": percentile(0.50),
        "p95": percentile(0.95),
    }


def tracking_metrics(counts: dict[str, int]) -> dict[str, float | int]:
    def value(name: str) -> int:
        item = counts.get(name, 0)
        if not isinstance(item, int) or item < 0:
            raise ValueError(f"{name} must be a non-negative integer")
        return item

    detection = binary_metrics(
        true_positives=value("detection_tp"),
        false_positives=value("detection_fp"),
        false_negatives=value("detection_fn"),
    )
    association = binary_metrics(
        true_positives=value("association_tp"),
        false_positives=value("association_fp"),
        false_negatives=value("association_fn"),
    )
    idtp = value("idtp")
    idfp = value("idfp")
    idfn = value("idfn")
    id_denominator = 2 * idtp + idfp + idfn
    idf1 = 2 * idtp / id_denominator if id_denominator else 0.0
    detection_accuracy_denominator = (
        detection.true_positives + detection.false_positives + detection.false_negatives
    )
    association_accuracy_denominator = (
        association.true_positives + association.false_positives + association.false_negatives
    )
    detection_accuracy = (
        detection.true_positives / detection_accuracy_denominator
        if detection_accuracy_denominator
        else 0.0
    )
    association_accuracy = (
        association.true_positives / association_accuracy_denominator
        if association_accuracy_denominator
        else 0.0
    )
    return {
        "hota": math.sqrt(detection_accuracy * association_accuracy),
        "idf1": idf1,
        "id_switches": value("id_switches"),
        "track_fragmentations": value("track_fragmentations"),
    }


def provenance(*, config: dict[str, object], dataset_hash: str) -> dict[str, object]:
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    try:
        git_revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        git_revision = "unknown"
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "config_hash": hashlib.sha256(canonical).hexdigest(),
        "dataset_hash": dataset_hash,
        "git_revision": git_revision,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def evaluate_manifest(payload: dict[str, object]) -> dict[str, object]:
    """Evaluate a compact, versioned Desk Change Set result manifest."""

    if payload.get("schema_version") != 1:
        raise ValueError("evaluation manifest schema_version must be 1")
    counts_object = payload.get("event_counts")
    if not isinstance(counts_object, dict):
        raise ValueError("evaluation manifest requires event_counts")
    counts = cast(dict[str, object], counts_object)
    confidences_object = payload.get("confidences", [])
    outcomes_object = payload.get("outcomes", [])
    latencies_object = payload.get("latency_ms", [])
    if not isinstance(confidences_object, list):
        raise ValueError("confidences must be a list")
    if not isinstance(outcomes_object, list):
        raise ValueError("outcomes must be a list")
    if not isinstance(latencies_object, list):
        raise ValueError("latency_ms must be a list")

    def count(name: str) -> int:
        value = counts.get(name, 0)
        if not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
        return value

    metrics = binary_metrics(
        true_positives=count("true_positives"),
        false_positives=count("false_positives"),
        false_negatives=count("false_negatives"),
    )
    confidences = [float(value) for value in confidences_object]
    outcomes = [bool(value) for value in outcomes_object]
    latencies = [float(value) for value in latencies_object]
    report: dict[str, object] = {
        "event_precision": metrics.precision,
        "event_recall": metrics.recall,
        "event_f1": metrics.f1,
        "calibration_ece": expected_calibration_error(confidences, outcomes),
        "latency": latency_summary(latencies),
    }
    tracking_object = payload.get("tracking_counts")
    if tracking_object is not None:
        if not isinstance(tracking_object, dict):
            raise ValueError("tracking_counts must be an object")
        report["tracking"] = tracking_metrics(cast(dict[str, int], tracking_object))

    sample_fields = (
        "mask_iou",
        "mask_boundary_f",
        "last_seen_timestamp_error_seconds",
        "last_seen_spatial_error_m",
        "reprojection_error_px",
        "scale_error_fraction",
        "completeness",
        "useful_update_rate_fps",
        "vram_peak_bytes",
        "ram_peak_bytes",
        "job_duration_seconds",
        "storage_bytes",
    )
    for field_name in sample_fields:
        values_object = payload.get(field_name)
        if values_object is None:
            continue
        if not isinstance(values_object, list):
            raise ValueError(f"{field_name} must be a list")
        report[field_name] = numeric_summary([float(value) for value in values_object])
    detection_map = payload.get("detection_map")
    if detection_map is not None:
        if isinstance(detection_map, bool) or not isinstance(detection_map, int | float):
            raise ValueError("detection_map must be numeric")
        value = float(detection_map)
        if not 0.0 <= value <= 1.0:
            raise ValueError("detection_map must be between 0 and 1")
        report["detection_map"] = value
    return report


def write_parquet_if_available(rows: list[dict[str, object]], destination: Path) -> bool:
    """Write canonical tabular results when the evaluation extra is installed."""

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        return False
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, destination)
    return True
