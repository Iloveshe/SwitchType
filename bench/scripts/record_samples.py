from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    from audio_checks import expected_wav_format_label, is_expected_wav_format, read_wav_info
except ModuleNotFoundError:
    from bench.scripts.audio_checks import expected_wav_format_label, is_expected_wav_format, read_wav_info

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.asr_config import resolve_whisper_settings


def load_samples(manifest: Path) -> list[dict[str, object]]:
    samples: list[dict[str, object]] = []
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            samples.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON on line {line_number}: {exc}") from exc
    return samples


def list_devices_command() -> list[str]:
    return ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""]


def has_listed_audio_device(output: str) -> bool:
    return bool(audio_devices(output))


def audio_devices(output: str) -> list[tuple[str, str]]:
    devices: list[tuple[str, str]] = []
    in_audio_section = False
    device_pattern = re.compile(r"\]\s+\[(\d+)\]\s+(.+)")
    for line in output.splitlines():
        if "AVFoundation audio devices:" in line:
            in_audio_section = True
            continue
        if "AVFoundation video devices:" in line:
            in_audio_section = False
            continue
        match = device_pattern.search(line)
        if in_audio_section and match:
            devices.append((f":{match.group(1)}", match.group(2).strip()))
    return devices


def recommended_audio_input(output: str) -> tuple[str, str] | None:
    devices = audio_devices(output)
    if not devices:
        return None
    for ffmpeg_input, name in devices:
        normalized = name.lower()
        if "microphone" in normalized or "mic" in normalized or "麦克风" in name:
            return ffmpeg_input, name
    return devices[0]


def audio_device_listing(run_command=None) -> str:
    if run_command is None:
        completed = subprocess.run(list_devices_command(), check=False, capture_output=True, text=True)
    else:
        completed = run_command(list_devices_command())
    return (completed.stdout or "") + (completed.stderr or "")


def format_audio_devices(devices: list[tuple[str, str]]) -> str:
    if not devices:
        return "(none)"
    return ", ".join(f"{ffmpeg_input} {name}" for ffmpeg_input, name in devices)


def normalized_audio_device_name(name: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", name.casefold())


def matching_audio_devices(devices: list[tuple[str, str]], ffmpeg_input_name: str) -> list[tuple[str, str]]:
    query = ffmpeg_input_name.strip().casefold()
    normalized_query = normalized_audio_device_name(ffmpeg_input_name)
    exact_matches = [(candidate_input, name) for candidate_input, name in devices if name.casefold() == query]
    normalized_matches = [
        (candidate_input, name)
        for candidate_input, name in devices
        if normalized_query and normalized_query in normalized_audio_device_name(name)
    ]
    return exact_matches or [(candidate_input, name) for candidate_input, name in devices if query in name.casefold()] or normalized_matches


def resolve_ffmpeg_input(ffmpeg_input: str, ffmpeg_input_name: str | None, run_command=None) -> str:
    if not ffmpeg_input_name:
        return ffmpeg_input
    if run_command is None and not shutil.which("ffmpeg"):
        raise SystemExit("--ffmpeg-input-name requires ffmpeg because it resolves macOS avfoundation device names.")

    output = audio_device_listing(run_command=run_command)
    devices = audio_devices(output)
    matches = matching_audio_devices(devices, ffmpeg_input_name)
    if len(matches) == 1:
        resolved_input, resolved_name = matches[0]
        print(f"Resolved recorder input: SWITCHTYPE_FFMPEG_INPUT={resolved_input} ({resolved_name})")
        return resolved_input
    available = format_audio_devices(devices)
    if not matches:
        raise SystemExit(f"No audio device matched {ffmpeg_input_name!r}. Available audio devices: {available}")
    raise SystemExit(f"Audio device name {ffmpeg_input_name!r} is ambiguous. Matching audio devices: {format_audio_devices(matches)}")


def run_list_devices(run_command=None, expected_device_name: str | None = None) -> int:
    if run_command is None:
        completed = subprocess.run(list_devices_command(), check=False, capture_output=True, text=True)
    else:
        completed = run_command(list_devices_command())
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    if has_listed_audio_device(output):
        devices = audio_devices(output)
        recommendation = recommended_audio_input(output)
        if recommendation is not None:
            ffmpeg_input, name = recommendation
            print(f"Recommended recorder input: SWITCHTYPE_FFMPEG_INPUT={ffmpeg_input} ({name})")
        if expected_device_name:
            matches = matching_audio_devices(devices, expected_device_name)
            if len(matches) == 1:
                ffmpeg_input, name = matches[0]
                print(f"Expected recorder input: SWITCHTYPE_FFMPEG_INPUT={ffmpeg_input} ({name})")
            elif not matches:
                print(
                    f"Expected audio device {expected_device_name!r} was not listed. Available audio devices: {format_audio_devices(devices)}",
                    file=sys.stderr,
                )
                return 3
            else:
                print(
                    f"Expected audio device {expected_device_name!r} is ambiguous. Matching audio devices: {format_audio_devices(matches)}",
                    file=sys.stderr,
                )
                return 3
        return 0
    print(
        "No avfoundation audio device was listed. Check macOS Microphone permission for the terminal app, "
        "then rerun make record-devices.",
        file=sys.stderr,
    )
    return 2


def recorder_command(output: Path, seconds: int, ffmpeg_input: str = ":0") -> list[str]:
    if shutil.which("ffmpeg"):
        return [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "avfoundation",
            "-i",
            ffmpeg_input,
            "-t",
            str(seconds),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(output),
        ]
    if shutil.which("rec"):
        return ["rec", "-r", "16000", "-c", "1", str(output), "trim", "0", str(seconds)]
    raise SystemExit("No recorder found. Install ffmpeg or sox/rec, then run this script again.")


def whisper_preview_command(
    audio_path: Path,
    root: Path = ROOT,
    environment: dict[str, str] | None = None,
) -> list[str]:
    settings = resolve_whisper_settings(root, environment)
    command = [settings.whisper_bin]
    if settings.whisper_no_gpu:
        command.append("-ng")
    command.extend(["-m", settings.whisper_model, "-f", str(audio_path), "-l", "auto", "-nt", "-np"])
    return command


def print_whisper_preview(
    audio_path: Path,
    root: Path = ROOT,
    environment: dict[str, str] | None = None,
    run_command=subprocess.run,
) -> None:
    command = whisper_preview_command(audio_path, root=root, environment=environment)
    print("ASR preview command:", " ".join(command))
    try:
        completed = run_command(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        print(f"ASR preview failed: {exc}")
        return
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        print(f"ASR preview failed with exit code {completed.returncode}: {detail}")
        return
    transcript = completed.stdout.strip()
    print("ASR preview:")
    print(transcript if transcript else "(empty)")


def wav_duration_seconds(path: Path) -> float | None:
    info = read_wav_info(path)
    return None if info is None else info.duration_seconds


def is_usable_audio(path: Path, min_duration: float) -> bool:
    if not path.exists() or path.stat().st_size <= 0:
        return False
    if path.suffix.lower() == ".wav":
        info = read_wav_info(path)
        return (
            info is not None
            and is_expected_wav_format(info)
            and info.has_signal
            and info.duration_seconds >= min_duration
        )
    duration = wav_duration_seconds(path)
    return duration is None or duration >= min_duration


def should_record(index: int, audio_path: Path, start_at: int, missing_only: bool, min_duration: float) -> bool:
    if index < start_at:
        return False
    if missing_only and is_usable_audio(audio_path, min_duration):
        return False
    return True


def selected_recordings(
    samples: list[dict[str, object]],
    start_at: int,
    missing_only: bool,
    min_duration: float,
    sample_id: str | None,
    limit: int | None,
) -> list[tuple[int, dict[str, object]]]:
    selected: list[tuple[int, dict[str, object]]] = []
    seen_sample_id = False
    for index, sample in enumerate(samples, start=1):
        current_id = str(sample["id"])
        audio_path = Path(str(sample["audio"]))
        if sample_id is not None:
            if current_id != sample_id:
                continue
            seen_sample_id = True
        if not should_record(index, audio_path, start_at, missing_only, min_duration):
            continue
        selected.append((index, sample))
        if limit is not None and len(selected) >= limit:
            break
    if sample_id is not None and not seen_sample_id:
        raise SystemExit(f"Sample id not found in manifest: {sample_id}")
    return selected


def sample_review_text(sample: dict[str, object]) -> str:
    lines = [f"参考文本：{sample['reference']}"]
    terms = sample.get("terms", [])
    if isinstance(terms, list) and terms:
        lines.append("保护词：" + ", ".join(str(term) for term in terms))
    return "\n".join(lines)


def validate_recording(audio_path: Path, min_duration: float) -> float | None:
    if not audio_path.exists():
        raise SystemExit(f"Recorder did not create audio file: {audio_path}")
    if audio_path.stat().st_size <= 0:
        raise SystemExit(f"Recorder created an empty audio file: {audio_path}")
    info = read_wav_info(audio_path) if audio_path.suffix.lower() == ".wav" else None
    if audio_path.suffix.lower() == ".wav":
        if info is None:
            raise SystemExit(f"Recording is not a readable WAV file: {audio_path}")
        if not is_expected_wav_format(info):
            raise SystemExit(f"Recording WAV format is not {expected_wav_format_label()}: {audio_path}")
        if not info.has_signal:
            raise SystemExit(f"Recording WAV file is silent: {audio_path}")
    duration = info.duration_seconds if info is not None else wav_duration_seconds(audio_path)
    if duration is not None and duration < min_duration:
        raise SystemExit(f"Recording is too short: {audio_path} is {duration:.2f}s, expected >= {min_duration:.2f}s")
    return duration


def record_with_retries(
    audio_path: Path,
    command: list[str],
    min_duration: float,
    max_attempts: int,
    countdown_seconds: int = 0,
    wait_for_prompt=input,
    preview_recording=None,
    review_text: str = "",
    recording_text: str = "",
    confirm_recording=None,
    sleep=time.sleep,
    run_command=subprocess.run,
) -> float | None:
    if max_attempts < 1:
        raise SystemExit("--max-attempts must be at least 1")
    if countdown_seconds < 0:
        raise SystemExit("--countdown-seconds must be at least 0")
    last_error: SystemExit | None = None
    for attempt in range(1, max_attempts + 1):
        if max_attempts > 1:
            print(f"第 {attempt}/{max_attempts} 次尝试")
        wait_for_prompt("准备好后按回车。录音开始前会再显示一次要读的句子...")
        for remaining in range(countdown_seconds, 0, -1):
            print(f"录音将在 {remaining} 秒后开始...")
            sleep(1)
        if recording_text:
            print()
            print("请读这句话：")
            print(recording_text)
            print()
        run_command(command, check=True)
        try:
            duration = validate_recording(audio_path, min_duration)
            if preview_recording is not None:
                preview_recording(audio_path)
            if review_text:
                print(review_text)
            if confirm_recording is not None:
                answer = confirm_recording("保留这条录音吗？输入 y 保留，直接回车重录：[y/N] ").strip().lower()
                if answer not in {"y", "yes"}:
                    audio_path.unlink(missing_ok=True)
                    message = "用户选择重录"
                    if attempt >= max_attempts:
                        raise SystemExit(message)
                    print(f"{message}。正在重新录这一条。")
                    continue
            return duration
        except SystemExit as exc:
            last_error = exc
            if attempt >= max_attempts:
                raise
            print(f"录音不合格：{exc}")
            audio_path.unlink(missing_ok=True)
            print("正在重新录这一条。")
    if last_error is not None:
        raise last_error
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Record SwitchType benchmark samples from a JSONL manifest.")
    parser.add_argument("--manifest", default=Path("bench/samples/manifest.30-template.jsonl"), type=Path)
    parser.add_argument("--seconds", default=8, type=int)
    parser.add_argument("--start-at", default=1, type=int)
    parser.add_argument("--missing-only", action="store_true", help="Skip samples that already have usable audio.")
    parser.add_argument("--sample-id", default=None, help="Record or re-record only one manifest sample id.")
    parser.add_argument("--limit", default=None, type=int, help="Record at most this many selected samples.")
    parser.add_argument("--min-duration", default=0.25, type=float, help="Minimum accepted WAV duration in seconds.")
    parser.add_argument("--max-attempts", default=2, type=int, help="Retry each rejected recording up to this many attempts.")
    parser.add_argument("--countdown-seconds", default=3, type=int, help="Seconds to wait after Return before recording starts.")
    parser.add_argument("--preview-asr", action="store_true", help="Run local whisper.cpp preview before asking to keep a sample.")
    parser.add_argument("--no-confirm", action="store_true", help="Do not ask before keeping each valid recording.")
    parser.add_argument(
        "--ffmpeg-input",
        default=os.environ.get("SWITCHTYPE_FFMPEG_INPUT", ":0"),
        help='ffmpeg avfoundation input for the microphone, for example ":0" or ":2".',
    )
    parser.add_argument(
        "--ffmpeg-input-name",
        default=os.environ.get("SWITCHTYPE_FFMPEG_INPUT_NAME"),
        help='Resolve the ffmpeg avfoundation microphone input by device name, for example "DJI MIC MINI".',
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List ffmpeg avfoundation devices to find the correct microphone input, then exit.",
    )
    parser.add_argument(
        "--expect-device-name",
        default=os.getenv("SWITCHTYPE_EXPECT_DEVICE_NAME"),
        help='When listing devices, require a matching microphone name, for example "DJI MIC MINI".',
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.list_devices:
        if not shutil.which("ffmpeg"):
            raise SystemExit("ffmpeg is required to list macOS avfoundation devices.")
        return run_list_devices(expected_device_name=args.expect_device_name)

    samples = load_samples(args.manifest)
    selected = selected_recordings(
        samples,
        start_at=args.start_at,
        missing_only=args.missing_only,
        min_duration=args.min_duration,
        sample_id=args.sample_id,
        limit=args.limit,
    )
    selected_indexes = {index for index, _ in selected}
    skipped = len(samples) - len(selected_indexes)
    ffmpeg_input = resolve_ffmpeg_input(args.ffmpeg_input, args.ffmpeg_input_name) if selected else args.ffmpeg_input
    for index, sample in selected:
        sample_id = str(sample["id"])
        audio_path = Path(str(sample["audio"]))
        reference = str(sample["reference"])
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"\n[{index}/{len(samples)}] {sample_id}")
        print(reference)
        print(f"Output: {audio_path}")
        command = recorder_command(audio_path, args.seconds, ffmpeg_input=ffmpeg_input)
        print("Command:", " ".join(command))
        if args.dry_run:
            continue
        duration = record_with_retries(
            audio_path,
            command,
            min_duration=args.min_duration,
            max_attempts=args.max_attempts,
            countdown_seconds=args.countdown_seconds,
            preview_recording=print_whisper_preview if args.preview_asr else None,
            review_text=sample_review_text(sample),
            recording_text=reference,
            confirm_recording=None if args.no_confirm else input,
        )
        if duration is None:
            print("Recorded audio file.")
        else:
            print(f"Recorded {duration:.2f}s.")
    print()
    print(f"Planned recordings: {len(selected)}")
    print(f"Skipped samples: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
