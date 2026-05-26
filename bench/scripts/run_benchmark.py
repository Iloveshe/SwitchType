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
    parser.add_argument("--generated-at", default=None, help="Override report generation timestamp for deterministic example reports.")
    args = parser.parse_args()

    result = run_benchmark(args.config, args.hotwords, args.manifest, args.report, generated_at=args.generated_at)
    print(f"Wrote {args.report} for {result.engine_count} engine(s) and {result.sample_count} sample(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
