from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any


def result_text(result: Any) -> str:
    if isinstance(result, list) and result:
        return result_text(result[0])
    if isinstance(result, dict):
        return str(result.get("text", "")).strip()
    return str(result or "").strip()


def optional_model(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if normalized.lower() in {"", "none", "off", "false", "disable", "disabled"}:
        return None
    return normalized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run SenseVoiceSmall through FunASR and write a transcript.")
    parser.add_argument("--model", default="iic/SenseVoiceSmall")
    parser.add_argument("--hub", default="ms", choices=["ms", "modelscope", "hf", "huggingface"])
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--language", default="auto")
    parser.add_argument("--batch-size-s", default=60, type=int)
    parser.add_argument("--vad-model", default="fsmn-vad")
    parser.add_argument("--max-single-segment-time", default=30000, type=int)
    parser.add_argument("--merge-vad", action="store_true")
    parser.add_argument("--merge-length-s", default=15, type=int)
    parser.add_argument("--cache-dir", default=os.environ.get("SWITCHTYPE_MODELSCOPE_CACHE", "models/modelscope-cache"), type=Path)
    args = parser.parse_args(argv)

    if not args.audio.exists():
        print(f"Audio file not found: {args.audio}", file=sys.stderr)
        return 2

    configure_modelscope_cache(args.cache_dir)

    try:
        from funasr import AutoModel
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
    except ModuleNotFoundError as error:
        print(
            "Missing FunASR dependency. Install it in your local environment before enabling SenseVoice: "
            f"{error}",
            file=sys.stderr,
        )
        return 2

    vad_model = optional_model(args.vad_model)
    vad_kwargs = None if vad_model is None else {"max_single_segment_time": args.max_single_segment_time}

    model = AutoModel(
        model=args.model,
        hub=args.hub,
        vad_model=vad_model,
        vad_kwargs=vad_kwargs,
        device=args.device,
    )
    generate_kwargs: dict[str, Any] = {
        "input": str(args.audio),
        "language": args.language,
        "use_itn": True,
        "batch_size_s": args.batch_size_s,
    }
    if args.merge_vad:
        generate_kwargs["merge_vad"] = True
        generate_kwargs["merge_length_s"] = args.merge_length_s

    raw_text = result_text(model.generate(**generate_kwargs))
    text = rich_transcription_postprocess(raw_text).strip()
    if not text:
        print("SenseVoice produced an empty transcript.", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text + "\n", encoding="utf-8")
    return 0


def configure_modelscope_cache(cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MODELSCOPE_CACHE"] = str(cache_dir)
    os.environ["MODELSCOPE_CREDENTIALS_PATH"] = str(cache_dir / "credentials")
    os.environ["HF_HOME"] = str(cache_dir / "huggingface")
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(cache_dir / "huggingface" / "hub")


if __name__ == "__main__":
    raise SystemExit(main())
