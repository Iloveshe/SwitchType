from __future__ import annotations

import os
from pathlib import Path

from scripts.asr_config import resolve_path


DEFAULT_HOTWORDS_CONFIG = "bench/config/hotwords.example.json"
PERSONAL_HOTWORDS_CONFIG = ".switchtype/hotwords.json"


def resolve_hotwords_path(
    root: Path,
    environment: dict[str, str] | None = None,
    *,
    home: Path | None = None,
    hotwords_config_path: str | None = None,
) -> Path:
    env = os.environ if environment is None else environment
    explicit_path = hotwords_config_path or env.get("SWITCHTYPE_HOTWORDS_CONFIG")
    if explicit_path:
        return resolve_path(root, explicit_path)

    home_dir = Path.home() if home is None else home
    personal = home_dir / PERSONAL_HOTWORDS_CONFIG
    if personal.is_file():
        return personal

    return root / DEFAULT_HOTWORDS_CONFIG
