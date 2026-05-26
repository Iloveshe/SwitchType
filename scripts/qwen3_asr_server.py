from __future__ import annotations

import argparse
import cgi
import json
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "Qwen/Qwen3-ASR-0.6B"


def dtype_from_name(name: str, device_map: str) -> Any:
    import torch

    normalized = name.strip().lower()
    if normalized == "auto":
        return torch.float32 if device_map == "cpu" else torch.bfloat16
    mapping = {
        "float32": torch.float32,
        "fp32": torch.float32,
        "float16": torch.float16,
        "fp16": torch.float16,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
    }
    if normalized not in mapping:
        raise ValueError(f"Unsupported dtype: {name}")
    return mapping[normalized]


def load_official_qwen3_asr_model(
    *,
    model_name: str,
    device_map: str,
    dtype: str,
    max_new_tokens: int,
    max_inference_batch_size: int,
) -> Any:
    try:
        from qwen_asr import Qwen3ASRModel
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing qwen-asr package. Install the official runtime with: "
            "python3 -m pip install -U qwen-asr"
        ) from exc

    return Qwen3ASRModel.from_pretrained(
        model_name,
        dtype=dtype_from_name(dtype, device_map),
        device_map=device_map,
        max_new_tokens=max_new_tokens,
        max_inference_batch_size=max_inference_batch_size,
    )


def parse_transcription_result(result: Any) -> dict[str, str]:
    item = result[0] if isinstance(result, list) else result
    if isinstance(item, dict):
        text = str(item.get("text") or "").strip()
        language = str(item.get("language") or "").strip()
    elif isinstance(item, str):
        text = item.strip()
        language = ""
    else:
        text = str(getattr(item, "text", "") or "").strip()
        language = str(getattr(item, "language", "") or "").strip()
    if not text:
        raise RuntimeError("Qwen3-ASR returned an empty transcript.")
    payload = {"text": text}
    if language:
        payload["language"] = language
    return payload


class Qwen3ASRRuntime:
    def __init__(
        self,
        *,
        model_name: str = DEFAULT_MODEL,
        language: str | None = "Chinese",
        device_map: str = "cpu",
        dtype: str = "auto",
        max_new_tokens: int = 256,
        max_inference_batch_size: int = 1,
    ):
        self.model_name = model_name
        self.language = None if language in (None, "", "auto", "Auto") else language
        self.device_map = device_map
        self.dtype = dtype
        self.max_new_tokens = max_new_tokens
        self.max_inference_batch_size = max_inference_batch_size
        self._model: Any | None = None
        self._lock = threading.Lock()

    def transcribe(self, audio: Path) -> dict[str, str]:
        payload, _ = self.transcribe_with_metrics(audio)
        return payload

    def transcribe_with_metrics(self, audio: Path) -> tuple[dict[str, str], dict[str, int | bool]]:
        model, load_metrics = self._load_model_with_metrics()
        infer_start = time.perf_counter()
        result = model.transcribe(audio=str(audio), language=self.language)
        infer_ms = int((time.perf_counter() - infer_start) * 1000)
        return parse_transcription_result(result), {
            **load_metrics,
            "infer_ms": infer_ms,
        }

    def warm_up(self) -> dict[str, int | bool]:
        _, metrics = self._load_model_with_metrics()
        return metrics

    @property
    def model_loaded(self) -> bool:
        return self._model is not None

    def _load_model(self) -> Any:
        model, _ = self._load_model_with_metrics()
        return model

    def _load_model_with_metrics(self) -> tuple[Any, dict[str, int | bool]]:
        with self._lock:
            model_loaded_before = self._model is not None
            start = time.perf_counter()
            if self._model is None:
                self._model = load_official_qwen3_asr_model(
                    model_name=self.model_name,
                    device_map=self.device_map,
                    dtype=self.dtype,
                    max_new_tokens=self.max_new_tokens,
                    max_inference_batch_size=self.max_inference_batch_size,
                )
            load_ms = int((time.perf_counter() - start) * 1000)
            return self._model, {
                "model_loaded_before": model_loaded_before,
                "load_ms": load_ms,
            }


class Qwen3ASRRequestHandler(BaseHTTPRequestHandler):
    runtime: Qwen3ASRRuntime
    audio_field: str = "audio"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._write_json({
                "ok": True,
                "model": self.runtime.model_name,
                "model_loaded": self.runtime.model_loaded,
                "device_map": self.runtime.device_map,
                "dtype": self.runtime.dtype,
                "language": self.runtime.language or "auto",
                "max_new_tokens": self.runtime.max_new_tokens,
            })
            return
        if self.path == "/warmup":
            start = time.perf_counter()
            metrics = self.runtime.warm_up()
            latency_ms = int((time.perf_counter() - start) * 1000)
            print(
                "qwen_asr_latency_ms "
                f"warmup={latency_ms} "
                f"load_ms={metrics['load_ms']} "
                f"model_loaded_before={metrics['model_loaded_before']} "
                f"device_map={self.runtime.device_map} "
                f"dtype={self.runtime.dtype}",
                flush=True,
            )
            self._write_json({
                "ok": True,
                "model": self.runtime.model_name,
                "model_loaded": self.runtime.model_loaded,
                "device_map": self.runtime.device_map,
                "dtype": self.runtime.dtype,
                "warmup_ms": latency_ms,
                **metrics,
            })
            return
        else:
            self.send_error(404, "Not found")
            return

    def do_POST(self) -> None:
        if self.path != "/transcribe":
            self.send_error(404, "Not found")
            return
        start = time.perf_counter()
        try:
            read_started = time.perf_counter()
            audio = self._read_audio_upload()
            read_upload_ms = int((time.perf_counter() - read_started) * 1000)
            write_started = time.perf_counter()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                temp_audio = Path(handle.name)
                handle.write(audio)
            write_temp_ms = int((time.perf_counter() - write_started) * 1000)
            try:
                payload, runtime_metrics = self.runtime.transcribe_with_metrics(temp_audio)
                server_total_ms = int((time.perf_counter() - start) * 1000)
                metrics = {
                    "server_total_ms": server_total_ms,
                    "read_upload_ms": read_upload_ms,
                    "write_temp_ms": write_temp_ms,
                    **runtime_metrics,
                }
                print(
                    "qwen_asr_latency_ms "
                    f"transcribe={server_total_ms} "
                    f"server_total_ms={server_total_ms} "
                    f"read_upload_ms={read_upload_ms} "
                    f"write_temp_ms={write_temp_ms} "
                    f"load_ms={runtime_metrics['load_ms']} "
                    f"infer_ms={runtime_metrics['infer_ms']} "
                    f"model_loaded_before={runtime_metrics['model_loaded_before']} "
                    f"bytes={len(audio)} "
                    f"chars={len(payload.get('text', ''))} "
                    f"device_map={self.runtime.device_map} "
                    f"dtype={self.runtime.dtype}",
                    flush=True,
                )
                self._write_json(payload, headers=self._latency_headers(metrics))
            finally:
                temp_audio.unlink(missing_ok=True)
        except Exception as exc:
            self._write_json({"error": str(exc)}, status=500)

    def _read_audio_upload(self) -> bytes:
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
            },
        )
        field = form[self.audio_field] if self.audio_field in form else None
        if field is None or not getattr(field, "file", None):
            raise RuntimeError(f"Missing multipart audio field: {self.audio_field}")
        data = field.file.read()
        if not data:
            raise RuntimeError("Uploaded audio field is empty.")
        return data

    def _write_json(
        self,
        payload: dict[str, object],
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _latency_headers(self, metrics: dict[str, int | bool]) -> dict[str, str]:
        headers = {
            "X-SwitchType-Server-Total-Ms": str(metrics["server_total_ms"]),
            "X-SwitchType-Server-Read-Upload-Ms": str(metrics["read_upload_ms"]),
            "X-SwitchType-Server-Write-Temp-Ms": str(metrics["write_temp_ms"]),
            "X-SwitchType-Server-Load-Ms": str(metrics["load_ms"]),
            "X-SwitchType-Server-Infer-Ms": str(metrics["infer_ms"]),
            "X-SwitchType-Server-Model-Loaded-Before": str(metrics["model_loaded_before"]).lower(),
            "X-SwitchType-Server-Device-Map": self.runtime.device_map,
            "X-SwitchType-Server-Dtype": self.runtime.dtype,
        }
        return headers

    def log_message(self, format: str, *args: object) -> None:
        return


def build_server(
    *,
    host: str,
    port: int,
    runtime: Qwen3ASRRuntime,
    audio_field: str,
) -> ThreadingHTTPServer:
    class Handler(Qwen3ASRRequestHandler):
        pass

    Handler.runtime = runtime
    Handler.audio_field = audio_field
    return ThreadingHTTPServer((host, port), Handler)


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve official Qwen3-ASR-0.6B behind SwitchType's http_json backend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--language", default="Chinese", help='Use "auto" for language identification.')
    parser.add_argument("--device-map", default="cpu")
    parser.add_argument("--dtype", default="auto")
    parser.add_argument("--max-new-tokens", default=256, type=int)
    parser.add_argument("--max-inference-batch-size", default=1, type=int)
    parser.add_argument("--audio-field", default="audio")
    return parser


def main() -> int:
    args = parser().parse_args()
    runtime = Qwen3ASRRuntime(
        model_name=args.model,
        language=args.language,
        device_map=args.device_map,
        dtype=args.dtype,
        max_new_tokens=args.max_new_tokens,
        max_inference_batch_size=args.max_inference_batch_size,
    )
    server = build_server(host=args.host, port=args.port, runtime=runtime, audio_field=args.audio_field)
    print(f"Serving {args.model} at http://{args.host}:{args.port}/transcribe")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
