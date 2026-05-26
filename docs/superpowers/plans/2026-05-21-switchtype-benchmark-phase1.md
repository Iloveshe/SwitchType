# SwitchType Benchmark Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working SwitchType CLI benchmark with deterministic post-processing, scoring, example configs, tests, and documentation.

**Architecture:** Phase 1 is a Python standard-library benchmark package under `bench/`. It uses file-based JSON/JSONL inputs, pluggable local ASR command runners, deterministic post-processing, pure-Python metrics, and Markdown report generation. The macOS app is not implemented in this phase, but the post-processing behavior and benchmark output are designed to feed the app phase.

**Tech Stack:** Python 3 standard library, `unittest`, JSON/JSONL config files, subprocess-based local ASR command invocation.

---

## File Structure

- Create: `.gitignore` for Python, Swift/Xcode, model files, generated reports, and local audio.
- Create: `README.md` with project purpose, phase status, benchmark usage, and app roadmap.
- Create: `bench/README.md` with benchmark input formats and commands.
- Create: `bench/config/benchmark.example.json` with fake, whisper.cpp, and SenseVoice/FunASR engine examples.
- Create: `bench/config/hotwords.example.json` with protected technical terms and replacements.
- Create: `bench/samples/manifest.example.jsonl` with example sample rows that do not require committed audio.
- Create: `bench/scripts/run_benchmark.py` as the CLI entry point.
- Create: `bench/scripts/score_transcripts.py` as a small CLI for scoring one reference/hypothesis pair.
- Create: `bench/switchtype_bench/__init__.py` for package exports.
- Create: `bench/switchtype_bench/asr.py` for ASR engine definitions and subprocess command execution.
- Create: `bench/switchtype_bench/config.py` for loading benchmark and hotword configs.
- Create: `bench/switchtype_bench/manifest.py` for JSONL sample loading.
- Create: `bench/switchtype_bench/metrics.py` for edit distance, CER, WER, and technical-term accuracy.
- Create: `bench/switchtype_bench/postprocess.py` for deterministic text normalization and hotword correction.
- Create: `bench/switchtype_bench/reporting.py` for Markdown benchmark reports.
- Create: `bench/switchtype_bench/runner.py` for orchestrating manifests, ASR engines, post-processing, metrics, and reports.
- Create: `bench/tests/test_metrics.py`.
- Create: `bench/tests/test_postprocess.py`.
- Create: `bench/tests/test_runner_smoke.py`.

## Task 1: Repository and Docs Skeleton

**Files:**
- Create: `.gitignore`
- Create: `README.md`
- Create: `bench/README.md`
- Create: `bench/config/benchmark.example.json`
- Create: `bench/config/hotwords.example.json`
- Create: `bench/samples/manifest.example.jsonl`

- [ ] **Step 1: Create `.gitignore`**

```gitignore
.DS_Store
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/
dist/
build/
DerivedData/
*.xcuserdata/
*.xcodeproj/project.xcworkspace/xcuserdata/
models/*.bin
models/*.gguf
bench/reports/
bench/outputs/
bench/samples/audio/
*.wav
*.m4a
*.mp3
```

- [ ] **Step 2: Create root README**

```markdown
# SwitchType

SwitchType is a local-first macOS voice typing tool for bilingual developer workflows.

Phase 1 builds the CLI benchmark: compare local ASR engines on Chinese-English technical speech, score accuracy and latency, and evaluate personal technical-term post-processing.

The macOS menu bar app comes after the benchmark proves the workflow.

## Current Scope

- CLI benchmark under `bench/`
- Deterministic hotword and replacement post-processing
- Metrics for character error rate, word error rate, and technical-term accuracy
- Example configs for `whisper.cpp` and SenseVoice/FunASR command runners

## Quick Start

```bash
python3 -m unittest discover -s bench/tests
python3 bench/scripts/run_benchmark.py \
  --config bench/config/benchmark.example.json \
  --hotwords bench/config/hotwords.example.json \
  --manifest bench/samples/manifest.example.jsonl
```

The example benchmark uses a fake ASR engine so the command works before local models are installed.

## Roadmap

- Add real local sample recordings
- Run `whisper.cpp` and SenseVoice/FunASR comparisons
- Build the macOS menu bar app with hold-to-record, local transcription, post-processing, and paste
- Add demo GIF and release setup notes
```

- [ ] **Step 3: Create benchmark README**

```markdown
# SwitchType Benchmark

The benchmark evaluates local ASR output against reference transcripts for Chinese-English developer dictation.

## Manifest Format

Each JSONL row describes one audio sample:

```json
{"id":"sample-001","audio":"bench/samples/audio/sample-001.wav","reference":"帮我看一下 Codex 的 PR issue 有没有过 CI","terms":["Codex","PR","issue","CI"]}
```

## Config Format

Engines are subprocess command templates. Tokens in braces are replaced by the runner.

- `{audio}`: input audio path
- `{output}`: temporary transcript output path
- `{model}`: model path from config

Use `type: "fake"` for local smoke tests.

## Commands

```bash
python3 -m unittest discover -s bench/tests
python3 bench/scripts/run_benchmark.py --config bench/config/benchmark.example.json --hotwords bench/config/hotwords.example.json --manifest bench/samples/manifest.example.jsonl
```
```

- [ ] **Step 4: Create example configs**

```json
{
  "timeout_seconds": 120,
  "engines": [
    {
      "name": "fake",
      "type": "fake",
      "transcript": "帮我看一下扣德克斯的皮阿尔 issue 有没有过 CI"
    },
    {
      "name": "whisper_cpp",
      "type": "command",
      "model": "models/ggml-large-v3-turbo.bin",
      "command": ["./third_party/whisper.cpp/main", "-m", "{model}", "-f", "{audio}", "-otxt", "-of", "{output_without_suffix}"]
    },
    {
      "name": "sensevoice_funasr",
      "type": "command",
      "model": "iic/SenseVoiceSmall",
      "command": ["python3", "-m", "funasr", "--model", "{model}", "--input", "{audio}", "--output", "{output}"]
    }
  ]
}
```

```json
{
  "protected_terms": ["Codex", "MCP", "SeaTalk", "prelive", "Go", "PR", "issue", "CI"],
  "replacements": {
    "扣德克斯": "Codex",
    "皮阿尔": "PR",
    "马克皮": "MCP",
    "勾语言": "Go"
  }
}
```

- [ ] **Step 5: Create example manifest**

```jsonl
{"id":"sample-001","audio":"bench/samples/audio/sample-001.wav","reference":"帮我看一下 Codex 的 PR issue 有没有过 CI","terms":["Codex","PR","issue","CI"]}
{"id":"sample-002","audio":"bench/samples/audio/sample-002.wav","reference":"这个 MCP server 在 prelive 环境连不上 SeaTalk","terms":["MCP","prelive","SeaTalk"]}
```

- [ ] **Step 6: Run docs status check**

Run: `find . -maxdepth 3 -type f | sort`

Expected: the files above are present.

- [ ] **Step 7: Commit**

```bash
git add .gitignore README.md bench/README.md bench/config/benchmark.example.json bench/config/hotwords.example.json bench/samples/manifest.example.jsonl
git commit -m "chore: add benchmark documentation skeleton"
```

## Task 2: Metrics Module

**Files:**
- Create: `bench/switchtype_bench/metrics.py`
- Create: `bench/tests/test_metrics.py`

- [ ] **Step 1: Write failing tests**

```python
import unittest

from switchtype_bench.metrics import (
    char_error_rate,
    technical_term_accuracy,
    word_error_rate,
)


class MetricsTests(unittest.TestCase):
    def test_char_error_rate_for_chinese_text(self):
        self.assertAlmostEqual(char_error_rate("你好 Codex", "你好 Code"), 1 / 7)

    def test_word_error_rate_for_english_tokens(self):
        self.assertAlmostEqual(word_error_rate("open PR issue", "open issue"), 1 / 3)

    def test_technical_term_accuracy_counts_present_terms(self):
        score = technical_term_accuracy(["Codex", "PR", "MCP"], "Codex opened PR")
        self.assertEqual(score, {"matched": 2, "total": 3, "accuracy": 2 / 3})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=bench python3 -m unittest bench/tests/test_metrics.py -v`

Expected: import failure because `switchtype_bench.metrics` does not exist yet.

- [ ] **Step 3: Implement metrics**

```python
from __future__ import annotations

import re
from typing import Iterable


def edit_distance(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for i, left_item in enumerate(left, start=1):
        current = [i]
        for j, right_item in enumerate(right, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (0 if left_item == right_item else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def char_error_rate(reference: str, hypothesis: str) -> float:
    reference_chars = [char for char in reference if not char.isspace()]
    hypothesis_chars = [char for char in hypothesis if not char.isspace()]
    if not reference_chars:
        return 0.0 if not hypothesis_chars else 1.0
    return edit_distance(reference_chars, hypothesis_chars) / len(reference_chars)


def _word_tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_+.-]+|[\u4e00-\u9fff]", text)


def word_error_rate(reference: str, hypothesis: str) -> float:
    reference_words = _word_tokens(reference)
    hypothesis_words = _word_tokens(hypothesis)
    if not reference_words:
        return 0.0 if not hypothesis_words else 1.0
    return edit_distance(reference_words, hypothesis_words) / len(reference_words)


def technical_term_accuracy(terms: Iterable[str], hypothesis: str) -> dict[str, float | int]:
    unique_terms = list(dict.fromkeys(terms))
    if not unique_terms:
        return {"matched": 0, "total": 0, "accuracy": 1.0}
    matched = sum(1 for term in unique_terms if term in hypothesis)
    return {"matched": matched, "total": len(unique_terms), "accuracy": matched / len(unique_terms)}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `PYTHONPATH=bench python3 -m unittest bench/tests/test_metrics.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add bench/switchtype_bench/metrics.py bench/tests/test_metrics.py
git commit -m "feat: add benchmark metrics"
```

## Task 3: Post-Processing Module

**Files:**
- Create: `bench/switchtype_bench/postprocess.py`
- Create: `bench/tests/test_postprocess.py`

- [ ] **Step 1: Write failing tests**

```python
import unittest

from switchtype_bench.postprocess import HotwordConfig, PostProcessor


class PostProcessorTests(unittest.TestCase):
    def test_replacements_and_whitespace(self):
        processor = PostProcessor(
            HotwordConfig(
                protected_terms=["Codex", "PR"],
                replacements={"扣德克斯": "Codex", "皮阿尔": "PR"},
            )
        )
        self.assertEqual(processor.process("  扣德克斯 的 皮阿尔  "), "Codex 的 PR")

    def test_ascii_token_spacing(self):
        processor = PostProcessor(HotwordConfig(protected_terms=["MCP"], replacements={}))
        self.assertEqual(processor.process("这个MCP server"), "这个 MCP server")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=bench python3 -m unittest bench/tests/test_postprocess.py -v`

Expected: import failure because `switchtype_bench.postprocess` does not exist yet.

- [ ] **Step 3: Implement post-processing**

```python
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class HotwordConfig:
    protected_terms: list[str]
    replacements: dict[str, str]


class PostProcessor:
    def __init__(self, config: HotwordConfig):
        self.config = config

    def process(self, text: str) -> str:
        output = text.strip()
        for source, target in self.config.replacements.items():
            output = output.replace(source, target)
        output = re.sub(r"\s+", " ", output)
        for term in self.config.protected_terms:
            output = self._space_ascii_term(output, term)
        return output.strip()

    def _space_ascii_term(self, text: str, term: str) -> str:
        if not term or not term.isascii():
            return text
        escaped = re.escape(term)
        text = re.sub(rf"([\u4e00-\u9fff])({escaped})", r"\1 \2", text)
        text = re.sub(rf"({escaped})([\u4e00-\u9fff])", r"\1 \2", text)
        return re.sub(r"\s+", " ", text)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `PYTHONPATH=bench python3 -m unittest bench/tests/test_postprocess.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add bench/switchtype_bench/postprocess.py bench/tests/test_postprocess.py
git commit -m "feat: add technical-term post processing"
```

## Task 4: Config, Manifest, ASR, Runner, and Reporting

**Files:**
- Create: `bench/switchtype_bench/__init__.py`
- Create: `bench/switchtype_bench/config.py`
- Create: `bench/switchtype_bench/manifest.py`
- Create: `bench/switchtype_bench/asr.py`
- Create: `bench/switchtype_bench/reporting.py`
- Create: `bench/switchtype_bench/runner.py`
- Create: `bench/tests/test_runner_smoke.py`

- [ ] **Step 1: Write smoke test**

```python
import json
import tempfile
import unittest
from pathlib import Path

from switchtype_bench.runner import run_benchmark


class RunnerSmokeTests(unittest.TestCase):
    def test_fake_engine_generates_markdown_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "benchmark.json"
            hotwords_path = root / "hotwords.json"
            manifest_path = root / "manifest.jsonl"
            report_path = root / "report.md"

            config_path.write_text(json.dumps({
                "timeout_seconds": 5,
            "engines": [{"name": "fake", "type": "fake", "enabled": True, "transcript": "扣德克斯 皮阿尔"}],
            }), encoding="utf-8")
            hotwords_path.write_text(json.dumps({
                "protected_terms": ["Codex", "PR"],
                "replacements": {"扣德克斯": "Codex", "皮阿尔": "PR"},
            }), encoding="utf-8")
            manifest_path.write_text(
                json.dumps({
                    "id": "sample-001",
                    "audio": "missing.wav",
                    "reference": "Codex PR",
                    "terms": ["Codex", "PR"],
                }, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            result = run_benchmark(config_path, hotwords_path, manifest_path, report_path)

            self.assertEqual(result.engine_count, 1)
            self.assertEqual(result.sample_count, 1)
            self.assertIn("| fake |", report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run smoke test to verify failure**

Run: `PYTHONPATH=bench python3 -m unittest bench/tests/test_runner_smoke.py -v`

Expected: import failure because `switchtype_bench.runner` does not exist yet.

- [ ] **Step 3: Implement package export**

```python
"""SwitchType benchmark package."""

__all__ = [
    "asr",
    "config",
    "manifest",
    "metrics",
    "postprocess",
    "reporting",
    "runner",
]
```

- [ ] **Step 4: Implement config loading**

```python
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from switchtype_bench.postprocess import HotwordConfig


@dataclass(frozen=True)
class EngineConfig:
    name: str
    type: str
    enabled: bool
    transcript: str | None = None
    command: list[str] | None = None
    model: str | None = None


@dataclass(frozen=True)
class BenchmarkConfig:
    timeout_seconds: int
    engines: list[EngineConfig]


def load_benchmark_config(path: Path) -> BenchmarkConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    engines = [
        EngineConfig(
            name=str(item["name"]),
            type=str(item["type"]),
            enabled=bool(item.get("enabled", True)),
            transcript=item.get("transcript"),
            command=item.get("command"),
            model=item.get("model"),
        )
        for item in data.get("engines", [])
    ]
    return BenchmarkConfig(timeout_seconds=int(data.get("timeout_seconds", 120)), engines=engines)


def load_hotword_config(path: Path) -> HotwordConfig:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return HotwordConfig(
        protected_terms=[str(term) for term in data.get("protected_terms", [])],
        replacements={str(key): str(value) for key, value in data.get("replacements", {}).items()},
    )
```

- [ ] **Step 5: Implement manifest loading**

```python
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Sample:
    id: str
    audio: Path
    reference: str
    terms: list[str]


def load_manifest(path: Path) -> list[Sample]:
    samples: list[Sample] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        data = json.loads(line)
        samples.append(
            Sample(
                id=str(data["id"]),
                audio=Path(str(data["audio"])),
                reference=str(data["reference"]),
                terms=[str(term) for term in data.get("terms", [])],
            )
        )
    return samples
```

- [ ] **Step 6: Implement ASR engines**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile


@dataclass(frozen=True)
class Transcription:
    text: str


class FakeEngine:
    def __init__(self, transcript: str):
        self.transcript = transcript

    def transcribe(self, audio: Path) -> Transcription:
        return Transcription(text=self.transcript)


class CommandEngine:
    def __init__(self, command: list[str], model: str | None, timeout_seconds: int):
        self.command = command
        self.model = model or ""
        self.timeout_seconds = timeout_seconds

    def transcribe(self, audio: Path) -> Transcription:
        if not audio.exists():
            raise FileNotFoundError(f"Audio file not found: {audio}")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "transcript.txt"
            output_without_suffix = output.with_suffix("")
            command = [
                part.format(
                    audio=str(audio),
                    output=str(output),
                    output_without_suffix=str(output_without_suffix),
                    model=self.model,
                )
                for part in self.command
            ]
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
            if output.exists():
                return Transcription(text=output.read_text(encoding="utf-8").strip())
            whisper_output = output_without_suffix.with_suffix(".txt")
            if whisper_output.exists():
                return Transcription(text=whisper_output.read_text(encoding="utf-8").strip())
            return Transcription(text=completed.stdout.strip())
```

- [ ] **Step 7: Implement reporting**

```python
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


def write_markdown_report(path: Path, rows: list[BenchmarkRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SwitchType Benchmark Report",
        "",
        "| Sample | Engine | Latency ms | CER | WER | Term Accuracy | Processed Transcript |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.sample_id} | {row.engine} | {row.latency_ms:.1f} | "
            f"{row.cer:.3f} | {row.wer:.3f} | {row.term_accuracy:.3f} | "
            f"{row.processed_text.replace('|', '/') } |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

- [ ] **Step 8: Implement runner**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

from switchtype_bench.asr import CommandEngine, FakeEngine
from switchtype_bench.config import EngineConfig, load_benchmark_config, load_hotword_config
from switchtype_bench.manifest import load_manifest
from switchtype_bench.metrics import char_error_rate, technical_term_accuracy, word_error_rate
from switchtype_bench.postprocess import PostProcessor
from switchtype_bench.reporting import BenchmarkRow, write_markdown_report


@dataclass(frozen=True)
class BenchmarkResult:
    engine_count: int
    sample_count: int
    rows: list[BenchmarkRow]


def _build_engine(config: EngineConfig, timeout_seconds: int):
    if config.type == "fake":
        return FakeEngine(config.transcript or "")
    if config.type == "command":
        if not config.command:
            raise ValueError(f"Engine {config.name} is missing command")
        return CommandEngine(config.command, config.model, timeout_seconds)
    raise ValueError(f"Unsupported engine type: {config.type}")


def run_benchmark(config_path: Path, hotwords_path: Path, manifest_path: Path, report_path: Path) -> BenchmarkResult:
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

    write_markdown_report(report_path, rows)
    return BenchmarkResult(engine_count=len(enabled_engines), sample_count=len(samples), rows=rows)
```

- [ ] **Step 9: Run all tests**

Run: `PYTHONPATH=bench python3 -m unittest discover -s bench/tests -v`

Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
git add bench/switchtype_bench bench/tests/test_runner_smoke.py
git commit -m "feat: add benchmark runner"
```

## Task 5: CLI Entry Points

**Files:**
- Create: `bench/scripts/run_benchmark.py`
- Create: `bench/scripts/score_transcripts.py`

- [ ] **Step 1: Add `run_benchmark.py`**

```python
from __future__ import annotations

import argparse
from pathlib import Path

from switchtype_bench.runner import run_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the SwitchType ASR benchmark.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--hotwords", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--report", default=Path("bench/reports/example.md"), type=Path)
    args = parser.parse_args()

    result = run_benchmark(args.config, args.hotwords, args.manifest, args.report)
    print(f"Wrote {args.report} for {result.engine_count} engine(s) and {result.sample_count} sample(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Add `score_transcripts.py`**

```python
from __future__ import annotations

import argparse
import json

from switchtype_bench.metrics import char_error_rate, technical_term_accuracy, word_error_rate


def main() -> int:
    parser = argparse.ArgumentParser(description="Score one transcript pair.")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--hypothesis", required=True)
    parser.add_argument("--term", action="append", default=[])
    args = parser.parse_args()

    print(json.dumps({
        "cer": char_error_rate(args.reference, args.hypothesis),
        "wer": word_error_rate(args.reference, args.hypothesis),
        "technical_terms": technical_term_accuracy(args.term, args.hypothesis),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run benchmark CLI smoke test**

Run:

```bash
PYTHONPATH=bench python3 bench/scripts/run_benchmark.py \
  --config bench/config/benchmark.example.json \
  --hotwords bench/config/hotwords.example.json \
  --manifest bench/samples/manifest.example.jsonl \
  --report bench/reports/example.md
```

Expected: command exits 0 and writes `bench/reports/example.md`.

- [ ] **Step 4: Run score CLI smoke test**

Run:

```bash
PYTHONPATH=bench python3 bench/scripts/score_transcripts.py \
  --reference "Codex PR issue" \
  --hypothesis "Codex issue" \
  --term Codex --term PR --term issue
```

Expected: command exits 0 and prints JSON with non-zero CER/WER and `matched` equal to 2.

- [ ] **Step 5: Commit**

```bash
git add bench/scripts/run_benchmark.py bench/scripts/score_transcripts.py bench/reports/example.md
git commit -m "feat: add benchmark CLI scripts"
```

## Task 6: Phase 1 Verification

**Files:**
- Modify: `README.md`
- Modify: `bench/README.md`

- [ ] **Step 1: Run unit tests**

Run: `PYTHONPATH=bench python3 -m unittest discover -s bench/tests -v`

Expected: all tests pass.

- [ ] **Step 2: Run benchmark example**

Run:

```bash
PYTHONPATH=bench python3 bench/scripts/run_benchmark.py \
  --config bench/config/benchmark.example.json \
  --hotwords bench/config/hotwords.example.json \
  --manifest bench/samples/manifest.example.jsonl \
  --report bench/reports/example.md
```

Expected: report contains one fake engine row per manifest sample.

- [ ] **Step 3: Check repository status**

Run: `git status --short`

Expected: only intended files are modified or untracked.

- [ ] **Step 4: Commit docs updates**

```bash
git add README.md bench/README.md bench/reports/example.md
git commit -m "docs: document benchmark phase"
```

## Spec Coverage Review

- CLI benchmark: covered by Tasks 1, 4, 5, and 6.
- Two local ASR paths: covered by Task 1 config examples and Task 4 command runner support.
- Accuracy and latency metrics: covered by Tasks 2 and 4.
- Technical-term correction: covered by Task 3.
- GitHub-ready README and setup docs: covered by Tasks 1 and 6.
- macOS menu bar app: deferred to Phase 2 because the approved design orders benchmark first, then app. Phase 2 must reuse the post-processing rules defined here.
