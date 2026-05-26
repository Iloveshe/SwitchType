from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_WHISPER_BIN = "third_party/whisper.cpp/build/bin/whisper-cli"
DEFAULT_WHISPER_MODEL = "third_party/whisper.cpp/models/ggml-large-v3-turbo.bin"


@dataclass(frozen=True)
class WhisperSettings:
    whisper_bin: str
    whisper_model: str
    whisper_no_gpu: bool


def resolve_whisper_settings(
    root: Path,
    environment: dict[str, str] | None = None,
    *,
    asr_config_path: str | None = None,
    whisper_bin: str | None = None,
    whisper_model: str | None = None,
    whisper_no_gpu: bool | None = None,
) -> WhisperSettings:
    env = os.environ if environment is None else environment
    config = load_asr_config(env, asr_config_path=asr_config_path)
    raw_bin = whisper_bin or env.get("SWITCHTYPE_WHISPER_BIN") or config.get("whisper_bin") or DEFAULT_WHISPER_BIN
    raw_model = whisper_model or env.get("SWITCHTYPE_WHISPER_MODEL") or config.get("whisper_model") or DEFAULT_WHISPER_MODEL
    return WhisperSettings(
        whisper_bin=str(resolve_path(root, raw_bin)),
        whisper_model=str(resolve_path(root, raw_model)),
        whisper_no_gpu=resolve_no_gpu(env, config, whisper_no_gpu),
    )


def load_asr_config(environment: dict[str, str] | None = None, *, asr_config_path: str | None = None) -> dict[str, Any]:
    uses_process_environment = environment is None
    env = os.environ if environment is None else environment
    for path in asr_config_candidates(
        env,
        asr_config_path=asr_config_path,
        include_process_home=uses_process_environment,
    ):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def asr_config_candidates(
    environment: dict[str, str],
    *,
    asr_config_path: str | None = None,
    include_process_home: bool = True,
) -> list[Path]:
    candidates: list[Path] = []
    explicit_path = asr_config_path or environment.get("SWITCHTYPE_ASR_CONFIG")
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())
    home = environment.get("HOME")
    if home:
        candidates.append(Path(home).expanduser() / ".switchtype/asr.json")
    elif include_process_home:
        candidates.append(Path.home() / ".switchtype/asr.json")
    return candidates


def resolve_path(root: Path, value: Any) -> Path:
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else root / path


def resolve_no_gpu(
    environment: dict[str, str],
    config: dict[str, Any],
    explicit_no_gpu: bool | None,
) -> bool:
    if explicit_no_gpu is not None:
        return explicit_no_gpu
    env_value = environment.get("SWITCHTYPE_WHISPER_NO_GPU")
    if env_value is not None:
        parsed = parse_bool(env_value)
        return bool(parsed)
    config_value = config.get("whisper_no_gpu")
    parsed = parse_bool(config_value)
    return bool(parsed)


def parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None
