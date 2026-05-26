from __future__ import annotations

import argparse
from pathlib import Path


START = "<!-- SWITCHTYPE_BENCHMARK_SUMMARY_START -->"
END = "<!-- SWITCHTYPE_BENCHMARK_SUMMARY_END -->"


def extract_engine_summary(report: str) -> str:
    marker = "## Engine Summary"
    start = report.find(marker)
    if start == -1:
        raise ValueError("report does not contain an Engine Summary section")
    sample_results = report.find("## Sample Results", start)
    if sample_results == -1:
        raise ValueError("report does not contain a Sample Results section")
    return report[start:sample_results].strip()


def update_readme(readme: str, summary: str) -> str:
    start = readme.find(START)
    end = readme.find(END)
    if start == -1 or end == -1 or end < start:
        raise ValueError("README benchmark summary markers are missing or invalid")
    before = readme[: start + len(START)]
    after = readme[end:]
    return f"{before}\n{summary}\n{after}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Update README benchmark summary from a SwitchType report.")
    parser.add_argument("--readme", default=Path("README.md"), type=Path)
    parser.add_argument("--report", default=Path("bench/reports/real-asr.md"), type=Path)
    args = parser.parse_args()

    summary = extract_engine_summary(args.report.read_text(encoding="utf-8"))
    updated = update_readme(args.readme.read_text(encoding="utf-8"), summary)
    args.readme.write_text(updated, encoding="utf-8")
    print(f"Updated {args.readme} from {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

