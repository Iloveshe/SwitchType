from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_release_ready import Check, benchmark_report_check, print_checks, strict_audio_check
from bench.scripts.update_public_benchmark_doc import build_document, build_readme_summary


DEFAULT_MANIFEST = "bench/samples/public/manifest.jsonl"
DEFAULT_REPORT = "bench/reports/public-asr.md"
DEFAULT_DOC = "docs/public-benchmark.md"
DEFAULT_README = "README.md"


def manifest_sample_count(manifest_path: str = DEFAULT_MANIFEST, root: Path = ROOT) -> int:
    target = root / manifest_path
    if not target.exists():
        return 0
    count = 0
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        json.loads(line)
        count += 1
    return count


def public_audio_check(
    manifest_path: str = DEFAULT_MANIFEST,
    expected_count: int | None = None,
    root: Path = ROOT,
) -> Check:
    count = expected_count if expected_count is not None else manifest_sample_count(manifest_path, root=root)
    if count <= 0:
        target = root / manifest_path
        detail = "manifest missing" if not target.exists() else "public manifest has no samples"
        return Check("public audio samples", False, detail)

    check = _with_readiness_root(root, lambda: strict_audio_check(manifest_path, count))
    return Check("public audio samples", check.ok, check.detail)


def public_benchmark_report_check(
    report_path: str = DEFAULT_REPORT,
    manifest_path: str = DEFAULT_MANIFEST,
    expected_count: int | None = None,
    root: Path = ROOT,
) -> Check:
    count = expected_count if expected_count is not None else manifest_sample_count(manifest_path, root=root)
    if count <= 0:
        return Check("public benchmark report", False, "public manifest has no samples")

    check = _with_readiness_root(
        root,
        lambda: benchmark_report_check(
            report_path,
            count,
            manifest_path=manifest_path,
        ),
    )
    return Check("public benchmark report", check.ok, check.detail)


def public_doc_check(
    report_path: str = DEFAULT_REPORT,
    doc_path: str = DEFAULT_DOC,
    root: Path = ROOT,
) -> Check:
    report = root / report_path
    doc = root / doc_path
    if not report.exists():
        return Check("public benchmark doc", False, "public report missing")
    if not doc.exists():
        return Check("public benchmark doc", False, "missing")

    expected = build_document(report.read_text(encoding="utf-8"), root=root)
    actual = doc.read_text(encoding="utf-8")
    if actual != expected:
        return Check("public benchmark doc", False, "stale; run make public-summary")
    return Check("public benchmark doc", True, "matches public report")


def public_readme_check(
    report_path: str = DEFAULT_REPORT,
    readme_path: str = DEFAULT_README,
    root: Path = ROOT,
) -> Check:
    report = root / report_path
    readme = root / readme_path
    if not report.exists():
        return Check("README public benchmark summary", False, "public report missing")
    if not readme.exists():
        return Check("README public benchmark summary", False, "missing")

    expected = build_readme_summary(report.read_text(encoding="utf-8"), root=root)
    actual = readme.read_text(encoding="utf-8")
    if expected not in actual:
        return Check("README public benchmark summary", False, "stale; run make public-summary")
    return Check("README public benchmark summary", True, "matches public report")


def collect_checks(
    root: Path = ROOT,
    manifest_path: str = DEFAULT_MANIFEST,
    report_path: str = DEFAULT_REPORT,
    doc_path: str = DEFAULT_DOC,
    readme_path: str = DEFAULT_README,
    expected_count: int | None = None,
) -> list[Check]:
    return [
        public_audio_check(manifest_path, expected_count=expected_count, root=root),
        public_benchmark_report_check(report_path, manifest_path, expected_count=expected_count, root=root),
        public_doc_check(report_path, doc_path, root=root),
        public_readme_check(report_path, readme_path, root=root),
    ]


def _with_readiness_root(root: Path, callback):
    import scripts.check_release_ready as release_ready

    original_root = release_ready.ROOT
    release_ready.ROOT = root
    try:
        return callback()
    finally:
        release_ready.ROOT = original_root


def main() -> int:
    parser = argparse.ArgumentParser(description="Check SwitchType public dataset benchmark evidence.")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, help="Public benchmark manifest JSONL path.")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="Public benchmark report path.")
    parser.add_argument("--doc", default=DEFAULT_DOC, help="Generated public benchmark document path.")
    parser.add_argument("--readme", default=DEFAULT_README, help="README path with generated public benchmark summary.")
    parser.add_argument(
        "--expected-count",
        type=int,
        help="Expected sample count. Defaults to the number of rows in the public manifest.",
    )
    args = parser.parse_args()

    checks = collect_checks(
        manifest_path=args.manifest,
        report_path=args.report,
        doc_path=args.doc,
        readme_path=args.readme,
        expected_count=args.expected_count,
    )
    failed = print_checks(checks)
    if failed:
        print()
        print("Public benchmark evidence is not ready. Run `make public-asr`, or import a permitted dataset with `make public-manifest` and then run `make public-benchmark`.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
