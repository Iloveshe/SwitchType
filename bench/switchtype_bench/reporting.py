from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BenchmarkRow:
    sample_id: str
    engine: str
    latency_ms: float
    raw_text: str
    processed_text: str
    cer: float
    wer: float
    term_matched: int
    term_total: int
    term_accuracy: float


@dataclass(frozen=True)
class EngineSummary:
    engine: str
    sample_count: int
    average_latency_ms: float
    average_cer: float
    average_wer: float
    term_accuracy: float


@dataclass(frozen=True)
class BenchmarkMetadata:
    generated_at: str
    config_path: str
    hotwords_path: str
    manifest_path: str
    report_path: str


def _cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ")


def summarize_by_engine(rows: list[BenchmarkRow]) -> list[EngineSummary]:
    grouped: dict[str, list[BenchmarkRow]] = {}
    for row in rows:
        grouped.setdefault(row.engine, []).append(row)

    summaries: list[EngineSummary] = []
    for engine, engine_rows in sorted(grouped.items()):
        sample_count = len(engine_rows)
        term_matched = sum(row.term_matched for row in engine_rows)
        term_total = sum(row.term_total for row in engine_rows)
        summaries.append(
            EngineSummary(
                engine=engine,
                sample_count=sample_count,
                average_latency_ms=sum(row.latency_ms for row in engine_rows) / sample_count,
                average_cer=sum(row.cer for row in engine_rows) / sample_count,
                average_wer=sum(row.wer for row in engine_rows) / sample_count,
                term_accuracy=(term_matched / term_total) if term_total else 1.0,
            )
        )
    return summaries


def write_markdown_report(path: Path, rows: list[BenchmarkRow], metadata: BenchmarkMetadata | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SwitchType Benchmark Report",
        "",
    ]
    if metadata is not None:
        lines.extend(
            [
                "## Run Metadata",
                "",
                f"- Generated at: {_cell(metadata.generated_at)}",
                f"- Config: {_cell(metadata.config_path)}",
                f"- Hotwords: {_cell(metadata.hotwords_path)}",
                f"- Manifest: {_cell(metadata.manifest_path)}",
                f"- Report: {_cell(metadata.report_path)}",
                "",
            ]
        )
    lines.extend(
        [
            "## Engine Summary",
            "",
            "| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for summary in summarize_by_engine(rows):
        lines.append(
            f"| {_cell(summary.engine)} | {summary.sample_count} | "
            f"{summary.average_latency_ms:.1f} | {summary.average_cer:.3f} | "
            f"{summary.average_wer:.3f} | {summary.term_accuracy:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Sample Results",
            "",
        ]
    )
    lines.extend(
        [
        "| Sample | Engine | Latency ms | CER | WER | Term Accuracy | Processed Transcript |",
        "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {_cell(row.sample_id)} | {_cell(row.engine)} | {row.latency_ms:.1f} | "
            f"{row.cer:.3f} | {row.wer:.3f} | {row.term_accuracy:.3f} | "
            f"{_cell(row.processed_text)} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
