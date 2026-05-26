from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from switchtype_bench.postprocess import HotwordConfig


@dataclass(frozen=True)
class EngineConfig:
    name: str
    type: str
    enabled: bool
    transcript: str | None = None
    command: list[str] | None = None
    model: str | None = None


@dataclass(frozen=True)
class BenchmarkConfig:
    timeout_seconds: int
    engines: list[EngineConfig]


def load_benchmark_config(path: Path) -> BenchmarkConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    engines = [
        EngineConfig(
            name=str(item["name"]),
            type=str(item["type"]),
            enabled=bool(item.get("enabled", True)),
            transcript=item.get("transcript"),
            command=item.get("command"),
            model=item.get("model"),
        )
        for item in data.get("engines", [])
    ]
    return BenchmarkConfig(timeout_seconds=int(data.get("timeout_seconds", 120)), engines=engines)


def load_hotword_config(path: Path) -> HotwordConfig:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return HotwordConfig(
        protected_terms=[str(term) for term in data.get("protected_terms", [])],
        replacements={str(key): str(value) for key, value in data.get("replacements", {}).items()},
    )

