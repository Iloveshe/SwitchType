from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_README_START = "<!-- SWITCHTYPE_PUBLIC_BENCHMARK_SUMMARY_START -->"
PUBLIC_README_END = "<!-- SWITCHTYPE_PUBLIC_BENCHMARK_SUMMARY_END -->"


def extract_section(text: str, start_marker: str, end_marker: str | None) -> str:
    start = text.find(start_marker)
    if start == -1:
        raise ValueError(f"report does not contain {start_marker}")
    end = text.find(end_marker, start + len(start_marker)) if end_marker else len(text)
    if end == -1:
        end = len(text)
    return text[start:end].strip()


def metadata_fields(report: str) -> dict[str, str]:
    metadata = extract_section(report, "## Run Metadata", "## Engine Summary")
    fields: dict[str, str] = {}
    for line in metadata.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        key, value = stripped.removeprefix("- ").split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def relative_repo_path(value: str, root: Path = ROOT) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        return value
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def engine_summary_sample_count(engine_summary: str) -> str:
    for line in engine_summary.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("|---") or stripped.startswith("| Engine"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) >= 2 and cells[1]:
            return cells[1]
    return "unknown"


def build_document(report: str, root: Path = ROOT) -> str:
    fields = metadata_fields(report)
    engine_summary = extract_section(report, "## Engine Summary", "## Sample Results")
    generated_at = fields.get("Generated at", "unknown")
    config = relative_repo_path(fields.get("Config", "unknown"), root=root)
    hotwords = relative_repo_path(fields.get("Hotwords", "unknown"), root=root)
    manifest = relative_repo_path(fields.get("Manifest", "unknown"), root=root)
    source_report = relative_repo_path(fields.get("Report", "unknown"), root=root)

    return "\n".join(
        [
            "# SwitchType Public Benchmark",
            "",
            "This document is generated from a local public-dataset ASR run. It is useful for comparing local ASR engines before personal recordings exist, but it is not personal microphone evidence and does not verify the global hotkey-to-paste UI workflow.",
            "",
            "## Dataset",
            "",
            "- Default source: [CAiRE/ASCEND](https://huggingface.co/datasets/CAiRE/ASCEND), filtered to Mandarin-English `language=mixed` rows.",
            "- Additional compatible sources: [BAAI/CS-Dialogue](https://huggingface.co/datasets/BAAI/CS-Dialogue), [MagicHub ASR-DevCECoMiCSC](https://magichub.com/datasets/dev-set-of-chinese-english-code-mixing-conversational-speech-corpus/), and [Mozilla Common Voice zh-CN](https://mozilladatacollective.com/datasets/cmn3iaztg00e4mb070uvufz7q) for monolingual Mandarin baseline work.",
            "- Third-party audio files are not committed; generated audio and reports stay under ignored local paths.",
            "",
            "## Reproduce",
            "",
            "```bash",
            "./.venv/bin/pip install -r requirements-public.txt",
            "make public-asr",
            "make public-readiness",
            "make public-summary",
            "```",
            "",
            "## Snapshot",
            "",
            f"- Generated at: `{generated_at}`",
            f"- Config: `{config}`",
            f"- Hotwords: `{hotwords}`",
            f"- Manifest: `{manifest}`",
            f"- Source report: `{source_report}`",
            "",
            engine_summary,
            "",
            "## Interpretation",
            "",
            "Use this table to decide which local ASR path is worth optimizing next. Treat the numbers as a reproducible smoke benchmark unless the sample count is large enough for the claim being made.",
            "",
        ]
    )


def build_readme_summary(report: str, root: Path = ROOT) -> str:
    engine_summary = extract_section(report, "## Engine Summary", "## Sample Results")
    readme_engine_summary = engine_summary.replace("## Engine Summary", "### Engine Summary", 1)
    sample_count = engine_summary_sample_count(engine_summary)

    return "\n".join(
        [
            f"Latest public benchmark: {sample_count} ASCEND mixed samples. Full snapshot: [docs/public-benchmark.md](docs/public-benchmark.md). This is public-data evidence, not personal microphone evidence.",
            "",
            readme_engine_summary,
        ]
    )


def replace_marked_region(text: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = text.find(start_marker)
    if start == -1:
        raise ValueError(f"document does not contain {start_marker}")
    end = text.find(end_marker, start + len(start_marker))
    if end == -1:
        raise ValueError(f"document does not contain {end_marker}")
    return text[: start + len(start_marker)] + "\n" + replacement.strip() + "\n" + text[end:]


def update_readme_public_summary(readme: str, summary: str) -> str:
    return replace_marked_region(readme, PUBLIC_README_START, PUBLIC_README_END, summary)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate docs/public-benchmark.md from a public ASR benchmark report.")
    parser.add_argument("--report", default=Path("bench/reports/public-asr.md"), type=Path)
    parser.add_argument("--output", default=Path("docs/public-benchmark.md"), type=Path)
    parser.add_argument("--readme", default=Path("README.md"), type=Path)
    args = parser.parse_args()

    report = args.report.read_text(encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_document(report), encoding="utf-8")
    print(f"Wrote {args.output}")
    if args.readme:
        readme = args.readme.read_text(encoding="utf-8")
        args.readme.write_text(update_readme_public_summary(readme, build_readme_summary(report)), encoding="utf-8")
        print(f"Updated {args.readme}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
