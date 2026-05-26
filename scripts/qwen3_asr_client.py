from __future__ import annotations

import argparse
import json
import mimetypes
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def extract_transcript(response_body: str) -> str:
    payload = json.loads(response_body)
    text = str(payload.get("text") or "").strip()
    if not text:
        raise RuntimeError(f"Qwen3-ASR response did not contain text: {response_body}")
    return text


def multipart_body(audio: Path, field_name: str, boundary: str) -> bytes:
    content_type = mimetypes.guess_type(str(audio))[0] or "audio/wav"
    data = audio.read_bytes()
    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        (
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{audio.name}"\r\n'
        ).encode("utf-8"),
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
        data,
        f"\r\n--{boundary}--\r\n".encode("utf-8"),
    ]
    return b"".join(parts)


def transcribe(url: str, audio: Path, field_name: str, timeout_seconds: float) -> str:
    if not audio.exists():
        raise FileNotFoundError(f"Audio file not found: {audio}")
    boundary = f"SwitchTypeQwen3Boundary-{uuid.uuid4()}"
    request = urllib.request.Request(
        url,
        data=multipart_body(audio, field_name, boundary),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Qwen3-ASR HTTP {exc.code}: {detail}") from exc
    return extract_transcript(body)


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send one WAV file to the local Qwen3-ASR HTTP backend.")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8765/transcribe")
    parser.add_argument("--field-name", default="audio")
    parser.add_argument("--timeout-seconds", default=180.0, type=float)
    return parser


def main() -> int:
    args = parser().parse_args()
    print(transcribe(args.url, args.audio, args.field_name, args.timeout_seconds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
