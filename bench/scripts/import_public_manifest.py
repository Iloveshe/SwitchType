from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REQUIRED_COLUMNS = ["id", "audio", "reference"]


@dataclass(frozen=True)
class DelimitedColumns:
    id: str = "id"
    audio: str = "audio"
    reference: str = "reference"
    terms: str = "terms"

    @property
    def required(self) -> list[str]:
        return [self.id, self.audio, self.reference]


def split_terms(value: str | None) -> list[str]:
    if not value:
        return []
    return [term.strip() for term in value.replace(",", ";").split(";") if term.strip()]


def rows_from_delimited(path: Path, columns: DelimitedColumns | None = None) -> Iterable[dict[str, str]]:
    columns = columns or DelimitedColumns()
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file, delimiter=delimiter)
        missing = [column for column in columns.required if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError("Missing required column(s): " + ", ".join(missing))
        for row in reader:
            yield {
                "id": row.get(columns.id, "") or "",
                "audio": row.get(columns.audio, "") or "",
                "reference": row.get(columns.reference, "") or "",
                "terms": row.get(columns.terms, "") or "",
            }


def parse_id_value_lines(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(maxsplit=1)
        if len(parts) != 2:
            continue
        rows[parts[0]] = parts[1].strip()
    return rows


def write_manifest_rows(rows: Iterable[dict[str, str]], output: Path, limit: int | None = None) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w", encoding="utf-8") as file:
        for row in rows:
            if limit is not None and count >= limit:
                break
            sample_id = row["id"].strip()
            audio = row["audio"].strip()
            reference = row["reference"].strip()
            if not sample_id or not audio or not reference:
                continue
            file.write(
                json.dumps(
                    {
                        "id": sample_id,
                        "audio": audio,
                        "reference": reference,
                        "terms": split_terms(row.get("terms")),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            count += 1
    return count


def import_manifest(
    source: Path,
    output: Path,
    limit: int | None = None,
    columns: DelimitedColumns | None = None,
) -> int:
    return write_manifest_rows(rows_from_delimited(source, columns=columns), output, limit)


def import_kaldi_manifest(wav_scp: Path, text: Path, output: Path, limit: int | None = None) -> int:
    audio_by_id = parse_id_value_lines(wav_scp)
    text_by_id = parse_id_value_lines(text)
    if not text_by_id:
        raise ValueError(f"No transcript rows found in {text}")
    rows = (
        {
            "id": sample_id,
            "audio": audio_path,
            "reference": text_by_id.get(sample_id, ""),
            "terms": "",
        }
        for sample_id, audio_path in audio_by_id.items()
    )
    return write_manifest_rows(rows, output, limit)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a locally downloaded public ASR dataset into a SwitchType JSONL manifest. "
            "CSV/TSV sources require id, audio, reference columns. Kaldi-style sources require wav.scp and text files."
        )
    )
    parser.add_argument("--source", type=Path, help="Input CSV/TSV with local audio paths and references.")
    parser.add_argument("--id-column", default="id", help="CSV/TSV column name for utterance id.")
    parser.add_argument("--audio-column", default="audio", help="CSV/TSV column name for local audio path.")
    parser.add_argument("--reference-column", default="reference", help="CSV/TSV column name for reference transcript.")
    parser.add_argument("--terms-column", default="terms", help="CSV/TSV column name for semicolon-separated hotword terms.")
    parser.add_argument("--wav-scp", type=Path, help="Kaldi-style wav.scp file with utterance id and audio path.")
    parser.add_argument("--text", type=Path, help="Kaldi-style text file with utterance id and transcript.")
    parser.add_argument("--output", required=True, type=Path, help="Output SwitchType JSONL manifest path.")
    parser.add_argument("--limit", type=int, default=None, help="Import only the first N valid rows.")
    args = parser.parse_args()

    if args.source:
        count = import_manifest(
            source=args.source,
            output=args.output,
            limit=args.limit,
            columns=DelimitedColumns(
                id=args.id_column,
                audio=args.audio_column,
                reference=args.reference_column,
                terms=args.terms_column,
            ),
        )
    elif args.wav_scp and args.text:
        count = import_kaldi_manifest(wav_scp=args.wav_scp, text=args.text, output=args.output, limit=args.limit)
    else:
        parser.error("provide either --source or both --wav-scp and --text")
    print(f"Wrote {count} sample(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
