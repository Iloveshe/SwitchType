from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Callable, Sequence


TIMEOUT_MARKER = b"--timeout-seconds"


def binary_supports_timeout(binary: Path) -> bool:
    try:
        return TIMEOUT_MARKER in binary.read_bytes()
    except OSError:
        return False


def run_hotkey_probe(
    binary: Path,
    timeout_seconds: str | int | float,
    package_command: str,
    runner: Callable[[list[str]], int] | None = None,
) -> int:
    if not binary.exists():
        print(f"Hotkey probe binary is missing: {binary}")
        print(f"Build it with: {package_command}")
        return 2
    if not binary_supports_timeout(binary):
        print(f"Hotkey probe binary does not support --timeout-seconds: {binary}")
        print(f"Rebuild it with: {package_command}")
        print("Then refresh packaged macOS permissions with: make app-request-permissions-packaged")
        return 2

    command = [str(binary), "--timeout-seconds", str(timeout_seconds)]
    return (runner or subprocess.call)(command)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SwitchTypeHotkeyProbe with stale-binary diagnostics.")
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--timeout-seconds", default="0")
    parser.add_argument("--package-command", default="make package")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return run_hotkey_probe(
        binary=args.binary,
        timeout_seconds=args.timeout_seconds,
        package_command=args.package_command,
    )


if __name__ == "__main__":
    raise SystemExit(main())
