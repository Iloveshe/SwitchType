from __future__ import annotations

import argparse
import json

from switchtype_bench.metrics import char_error_rate, technical_term_accuracy, word_error_rate


def main() -> int:
    parser = argparse.ArgumentParser(description="Score one transcript pair.")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--hypothesis", required=True)
    parser.add_argument("--term", action="append", default=[])
    args = parser.parse_args()

    print(
        json.dumps(
            {
                "cer": char_error_rate(args.reference, args.hypothesis),
                "wer": word_error_rate(args.reference, args.hypothesis),
                "technical_terms": technical_term_accuracy(args.term, args.hypothesis),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

