from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Protocol

from switchtype_bench.asr import CommandEngine, FakeEngine, Transcription
from switchtype_bench.config import EngineConfig, load_benchmark_config, load_hotword_config
from switchtype_bench.manifest import load_manifest
from switchtype_bench.metrics import char_error_rate, technical_term_accuracy, word_error_rate
from switchtype_bench.postprocess import PostProcessor
from switchtype_bench.reporting import BenchmarkMetadata, BenchmarkRow, write_markdown_report


class AsrEngine(Protocol):
    def transcribe(self, audio: Path) -> Transcription:
        ...


@dataclass(frozen=True)
class BenchmarkResult:
    engine_count: int
    sample_count: int
    rows: list[BenchmarkRow]


def _build_engine(config: EngineConfig, timeout_seconds: int) -> AsrEngine:
    if config.type == "fake":
        return FakeEngine(config.transcript or "")
    if config.type == "command":
        if not config.command:
            raise ValueError(f"Engine {config.name} is missing command")
        return CommandEngine(config.command, config.model, timeout_seconds)
    raise ValueError(f"Unsupported engine type: {config.type}")


def run_benchmark(
    config_path: Path,
    hotwords_path: Path,
    manifest_path: Path,
    report_path: Path,
    generated_at: str | None = None,
) -> BenchmarkResult:
    benchmark_config = load_benchmark_config(config_path)
    hotword_config = load_hotword_config(hotwords_path)
    processor = PostProcessor(hotword_config)
    samples = load_manifest(manifest_path)
    enabled_engines = [engine for engine in benchmark_config.engines if engine.enabled]
    rows: list[BenchmarkRow] = []

    for engine_config in enabled_engines:
        engine = _build_engine(engine_config, benchmark_config.timeout_seconds)
        for sample in samples:
            started = time.perf_counter()
            transcription = engine.transcribe(sample.audio)
            latency_ms = (time.perf_counter() - started) * 1000
            processed = processor.process(transcription.text)
            term_score = technical_term_accuracy(sample.terms, processed)
            rows.append(
                BenchmarkRow(
                    sample_id=sample.id,
                    engine=engine_config.name,
                    latency_ms=latency_ms,
                    raw_text=transcription.text,
                    processed_text=processed,
                    cer=char_error_rate(sample.reference, processed),
                    wer=word_error_rate(sample.reference, processed),
                    term_matched=int(term_score["matched"]),
                    term_total=int(term_score["total"]),
                    term_accuracy=float(term_score["accuracy"]),
                )
            )

    write_markdown_report(
        report_path,
        rows,
        metadata=BenchmarkMetadata(
            generated_at=generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            config_path=str(config_path),
            hotwords_path=str(hotwords_path),
            manifest_path=str(manifest_path),
            report_path=str(report_path),
        ),
    )
    return BenchmarkResult(engine_count=len(enabled_engines), sample_count=len(samples), rows=rows)
