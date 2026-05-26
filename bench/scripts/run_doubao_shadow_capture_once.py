from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path


RunFunc = Callable[[list[str]], object]


def return_code(result: object) -> int:
    return int(getattr(result, "returncode", 1))


def run_step(name: str, command: list[str], run_func: RunFunc) -> int:
    print(f"==> {name}: {' '.join(command)}")
    return return_code(run_func(command))


def latest_segment_identity(segments_path: Path) -> tuple[str, str] | None:
    try:
        lines = segments_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        text = line.strip()
        if not text:
            continue
        # Keep this parser intentionally narrow: identity only needs stable text keys.
        import json

        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            return (text, "")
        return (str(row.get("id") or ""), str(row.get("audio") or ""))
    return None


def run_capture_once(
    run_func: RunFunc | None = None,
    make_command: str | None = None,
    segments_path: Path = Path("bench/samples/doubao-shadow/segments.jsonl"),
) -> int:
    runner = run_func or (lambda command: subprocess.run(command, check=False))
    make = make_command or os.environ.get("MAKE", "make")
    before_identity = latest_segment_identity(segments_path)

    record_code = run_step(
        "fixed-duration recording",
        [make, "doubao-shadow-record-seconds-auto-packaged"],
        runner,
    )
    if record_code == 0:
        after_identity = latest_segment_identity(segments_path)
        if after_identity is not None and after_identity != before_identity:
            preview_code = run_step(
                "latest local ASR preview",
                [make, "doubao-shadow-latest-preview"],
                runner,
            )
            if preview_code != 0:
                print("Latest preview failed; continuing to status.")
        else:
            print("Skipping latest preview because no new shadow segment was written.")
            record_code = 1
    else:
        print("Skipping latest preview because fixed-duration recording failed.")

    status_code = run_step("shadow status", [make, "doubao-shadow-status"], runner)
    if record_code != 0:
        return record_code
    return status_code


def main() -> int:
    return run_capture_once()


if __name__ == "__main__":
    sys.exit(main())
