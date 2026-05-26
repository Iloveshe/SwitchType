from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"protected_terms": [], "replacements": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {"protected_terms": [], "replacements": {}}


def manifest_terms(path: Path) -> list[str]:
    if not path.exists():
        return []
    terms: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        terms.extend(str(term) for term in data.get("terms", []))
    return terms


def unique_nonempty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        item = value.strip()
        if not item or item in seen:
            continue
        output.append(item)
        seen.add(item)
    return output


def parse_replacement(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("replacement must use source=target")
    source, target = value.split("=", 1)
    if not source or not target:
        raise argparse.ArgumentTypeError("replacement source and target must be non-empty")
    return source, target


def build_hotwords_config(
    base_config: Path,
    manifest: Path,
    replacement_overrides: list[tuple[str, str]],
) -> dict[str, object]:
    base = load_json(base_config)
    protected_terms = unique_nonempty(
        [str(term) for term in base.get("protected_terms", [])]
        + manifest_terms(manifest)
    )
    replacements = {str(key): str(value) for key, value in base.get("replacements", {}).items()}
    replacements.update(dict(replacement_overrides))
    return {
        "protected_terms": protected_terms,
        "replacements": replacements,
    }


def write_config(output: Path, config: dict[str, object], force: bool) -> None:
    if output.exists() and not force:
        raise SystemExit(f"{output} already exists; pass --force to overwrite it.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a SwitchType personal hotwords config.")
    parser.add_argument("--base-config", default=Path("bench/config/hotwords.example.json"), type=Path)
    parser.add_argument("--manifest", default=Path("bench/samples/manifest.30-template.jsonl"), type=Path)
    parser.add_argument("--output", default=Path.home() / ".switchtype/hotwords.json", type=Path)
    parser.add_argument("--replacement", action="append", default=[], type=parse_replacement, help="Add or override a replacement as source=target.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing config file.")
    args = parser.parse_args()

    config = build_hotwords_config(
        base_config=args.base_config,
        manifest=args.manifest,
        replacement_overrides=args.replacement,
    )
    write_config(args.output.expanduser(), config, args.force)
    print(f"Wrote {args.output.expanduser()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
