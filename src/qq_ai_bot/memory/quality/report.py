"""Content-safe JSON, Markdown, and JUnit quality reports."""

from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

from qq_ai_bot.memory.quality.models import MemoryQualityReport


def write_reports(directory: Path, report: MemoryQualityReport) -> tuple[Path, Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "report.json"
    md_path = directory / "report.md"
    junit_path = directory / "junit.xml"
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    metric_rows = "\n".join(
        f"| `{name}` | {item.value if item.value is not None else 'null'} | "
        f"{item.numerator:g}/{item.denominator:g} |"
        for name, item in sorted(report.metrics.items())
    )
    failed_ids = [item.case_id for item in report.cases if not item.passed]
    md_path.write_text(
        "\n".join(
            (
                "# Memory V2 Quality Report",
                "",
                f"- Suite: `{report.suite_version}` / `{report.suite_mode.value}`",
                f"- Commit: `{report.commit}`",
                f"- Dataset: `{report.dataset_hash}`",
                f"- Cases: {report.passed_count}/{report.case_count} passed",
                f"- Failed IDs: {', '.join(failed_ids) if failed_ids else 'none'}",
                f"- Duration: {report.duration_seconds:.3f}s",
                "",
                "| Metric | Value | Numerator/denominator |",
                "|---|---:|---:|",
                metric_rows,
                "",
            )
        ),
        encoding="utf-8",
    )
    suite = Element(
        "testsuite",
        name="memory-quality",
        tests=str(report.case_count),
        failures=str(report.failed_count),
        time=f"{report.duration_seconds:.6f}",
    )
    for item in report.cases:
        test = SubElement(suite, "testcase", classname=item.category, name=item.case_id)
        if not item.passed:
            failure = SubElement(test, "failure", message="; ".join(item.failures))
            failure.text = "\n".join(item.failures)
    junit_path.write_bytes(b'<?xml version="1.0" encoding="utf-8"?>\n' + tostring(suite))
    return json_path, md_path, junit_path
