from __future__ import annotations

import argparse
import json
from pathlib import Path


def default_config_path() -> Path:
    return Path.home() / ".switchtype" / "asr.json"


def write_config(path: Path, *, url: str, timeout_seconds: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    payload.update(
        {
            "asr_backend": "http_json",
            "asr_http_profile": "qwen3_official_local",
            "asr_http_url": url,
            "asr_http_field_name": "audio",
            "asr_http_transcript_key": "text",
            "timeout_seconds": timeout_seconds,
        }
    )
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Point SwitchType at a local official Qwen3-ASR HTTP server.")
    parser.add_argument("--path", default=default_config_path(), type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8765/transcribe")
    parser.add_argument("--timeout-seconds", default=180, type=int)
    return parser


def main() -> int:
    args = parser().parse_args()
    path = write_config(args.path, url=args.url, timeout_seconds=args.timeout_seconds)
    print(f"Wrote Qwen3-ASR HTTP backend config to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
