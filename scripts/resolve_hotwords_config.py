from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.hotwords_config import resolve_hotwords_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve SwitchType hotword config path.")
    parser.add_argument("--hotwords-config", default="", help="Explicit hotwords JSON path.")
    args = parser.parse_args()

    path = resolve_hotwords_path(
        ROOT,
        hotwords_config_path=args.hotwords_config or None,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
