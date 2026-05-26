from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Sample:
    id: str
    audio: Path
    reference: str
    terms: list[str]


def load_manifest(path: Path) -> list[Sample]:
    samples: list[Sample] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on manifest line {line_number}: {exc}") from exc
        samples.append(
            Sample(
                id=str(data["id"]),
                audio=Path(str(data["audio"])),
                reference=str(data["reference"]),
                terms=[str(term) for term in data.get("terms", [])],
            )
        )
    return samples

