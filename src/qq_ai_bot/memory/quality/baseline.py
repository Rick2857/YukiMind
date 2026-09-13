"""Explicit baseline read/write helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from qq_ai_bot.memory.quality.models import (
    MemoryQualityReport,
    QualityBaseline,
    QualityPerformanceReport,
)


def load_baseline(path: Path) -> QualityBaseline:
    return QualityBaseline.model_validate_json(path.read_text(encoding="utf-8"))


def baseline_from_report(
    report: MemoryQualityReport,
    *,
    performance: QualityPerformanceReport | None = None,
) -> QualityBaseline:
    return QualityBaseline(
        suite_version=report.suite_version,
        commit=report.commit,
        python_version=report.python_version,
        sqlite_version=report.sqlite_version,
        generated_at=datetime.now(UTC),
        dataset_hash=report.dataset_hash,
        gate_config_hash=report.gate_config_hash,
        fake_model_id=report.fake_model_id,
        fake_embedding_id=report.fake_embedding_id,
        case_count=report.case_count,
        metrics={name: metric.value for name, metric in sorted(report.metrics.items())},
        performance=performance,
    )


def write_baseline(path: Path, report: MemoryQualityReport) -> QualityBaseline:
    previous = load_baseline(path) if path.exists() else None
    baseline = baseline_from_report(
        report,
        performance=previous.performance if previous is not None else None,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(baseline.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return baseline


def write_performance_baseline(
    path: Path,
    performance: QualityPerformanceReport,
) -> QualityBaseline:
    """Attach one explicitly measured scenario to an existing quality baseline."""

    baseline = load_baseline(path)
    updated = baseline.model_copy(update={"performance": performance})
    path.write_text(updated.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return updated
