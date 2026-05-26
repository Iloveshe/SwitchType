import contextlib
import io
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from bench.scripts.record_samples import (
    has_listed_audio_device,
    is_usable_audio,
    list_devices_command,
    recommended_audio_input,
    record_with_retries,
    recorder_command,
    resolve_ffmpeg_input,
    run_list_devices,
    sample_review_text,
    selected_recordings,
    should_record,
    validate_recording,
    whisper_preview_command,
    wav_duration_seconds,
)


def write_test_wav(
    path: Path,
    seconds: float = 0.25,
    rate: int = 16000,
    channels: int = 1,
    signal: bool = True,
) -> None:
    frames = int(seconds * rate)
    sample = b"\x01\x00" if signal else b"\x00\x00"
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(sample * frames * channels)


class RecordSamplesTests(unittest.TestCase):
    def test_ffmpeg_recorder_command_uses_default_mac_input(self):
        with patch("bench.scripts.record_samples.shutil.which", side_effect=lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None):
            command = recorder_command(Path("out.wav"), seconds=4)

        self.assertEqual(command[:10], ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "avfoundation", "-i", ":0", "-t"])
        self.assertEqual(command[-5:], ["-ar", "16000", "-ac", "1", "out.wav"])

    def test_ffmpeg_recorder_command_uses_configured_mac_input(self):
        with patch("bench.scripts.record_samples.shutil.which", side_effect=lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None):
            command = recorder_command(Path("out.wav"), seconds=4, ffmpeg_input=":2")

        self.assertEqual(command[:9], ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "avfoundation", "-i", ":2"])

    def test_list_devices_command_shows_avfoundation_inputs(self):
        self.assertEqual(
            list_devices_command(),
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        )

    def test_has_listed_audio_device_detects_avfoundation_audio_entries(self):
        output = (
            "[AVFoundation indev @ 0x123] AVFoundation video devices:\n"
            "[AVFoundation indev @ 0x123] [0] FaceTime HD Camera\n"
            "[AVFoundation indev @ 0x123] AVFoundation audio devices:\n"
            "[AVFoundation indev @ 0x123] [0] MacBook Pro Microphone\n"
        )

        self.assertTrue(has_listed_audio_device(output))

    def test_has_listed_audio_device_rejects_empty_audio_section(self):
        output = (
            "[AVFoundation indev @ 0x123] AVFoundation video devices:\n"
            "[AVFoundation indev @ 0x123] AVFoundation audio devices:\n"
            "[in#0 @ 0x456] Error opening input: Input/output error\n"
        )

        self.assertFalse(has_listed_audio_device(output))

    def test_recommended_audio_input_prefers_builtin_microphone(self):
        output = (
            "[AVFoundation indev @ 0x123] AVFoundation audio devices:\n"
            "[AVFoundation indev @ 0x123] [0] ZoomAudioDevice\n"
            "[AVFoundation indev @ 0x123] [1] MacBook Pro麦克风\n"
        )

        self.assertEqual(recommended_audio_input(output), (":1", "MacBook Pro麦克风"))

    def test_recommended_audio_input_falls_back_to_first_audio_device(self):
        output = (
            "[AVFoundation indev @ 0x123] AVFoundation audio devices:\n"
            "[AVFoundation indev @ 0x123] [0] External USB Audio\n"
            "[AVFoundation indev @ 0x123] [1] ZoomAudioDevice\n"
        )

        self.assertEqual(recommended_audio_input(output), (":0", "External USB Audio"))

    def test_run_list_devices_fails_when_no_audio_device_is_listed(self):
        completed = subprocess.CompletedProcess(
            args=list_devices_command(),
            returncode=1,
            stdout="",
            stderr="[AVFoundation indev @ 0x123] AVFoundation audio devices:\n",
        )

        with contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()) as stderr:
            code = run_list_devices(run_command=lambda command: completed)

        self.assertEqual(code, 2)
        self.assertIn("AVFoundation audio devices", stdout.getvalue())
        self.assertIn("No avfoundation audio device was listed", stderr.getvalue())

    def test_run_list_devices_succeeds_when_audio_device_is_listed(self):
        completed = subprocess.CompletedProcess(
            args=list_devices_command(),
            returncode=1,
            stdout="",
            stderr=(
                "[AVFoundation indev @ 0x123] AVFoundation audio devices:\n"
                "[AVFoundation indev @ 0x123] [0] MacBook Pro Microphone\n"
            ),
        )

        with contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()) as stderr:
            code = run_list_devices(run_command=lambda command: completed)

        self.assertEqual(code, 0)
        self.assertIn("MacBook Pro Microphone", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_run_list_devices_prints_recommended_input(self):
        completed = subprocess.CompletedProcess(
            args=list_devices_command(),
            returncode=1,
            stdout="",
            stderr=(
                "[AVFoundation indev @ 0x123] AVFoundation audio devices:\n"
                "[AVFoundation indev @ 0x123] [0] ZoomAudioDevice\n"
                "[AVFoundation indev @ 0x123] [1] MacBook Pro麦克风\n"
            ),
        )

        with contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
            code = run_list_devices(run_command=lambda command: completed)

        self.assertEqual(code, 0)
        self.assertIn("Recommended recorder input: SWITCHTYPE_FFMPEG_INPUT=:1", stdout.getvalue())
        self.assertIn("MacBook Pro麦克风", stdout.getvalue())

    def test_run_list_devices_can_confirm_expected_device_name(self):
        completed = subprocess.CompletedProcess(
            args=list_devices_command(),
            returncode=1,
            stdout="",
            stderr=(
                "[AVFoundation indev @ 0x123] AVFoundation audio devices:\n"
                "[AVFoundation indev @ 0x123] [0] MacBook Pro麦克风\n"
                "[AVFoundation indev @ 0x123] [2] DJI MIC MINI\n"
            ),
        )

        with contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
            code = run_list_devices(run_command=lambda command: completed, expected_device_name="dji-mic")

        self.assertEqual(code, 0)
        self.assertIn("Expected recorder input: SWITCHTYPE_FFMPEG_INPUT=:2 (DJI MIC MINI)", stdout.getvalue())

    def test_run_list_devices_fails_when_expected_device_name_is_missing(self):
        completed = subprocess.CompletedProcess(
            args=list_devices_command(),
            returncode=1,
            stdout="",
            stderr=(
                "[AVFoundation indev @ 0x123] AVFoundation audio devices:\n"
                "[AVFoundation indev @ 0x123] [0] MacBook Pro麦克风\n"
            ),
        )

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as stderr:
            code = run_list_devices(run_command=lambda command: completed, expected_device_name="DJI MIC MINI")

        self.assertEqual(code, 3)
        self.assertIn("Expected audio device 'DJI MIC MINI' was not listed", stderr.getvalue())
        self.assertIn("MacBook Pro麦克风", stderr.getvalue())

    def test_resolve_ffmpeg_input_uses_exact_device_name_match(self):
        completed = subprocess.CompletedProcess(
            args=list_devices_command(),
            returncode=1,
            stdout="",
            stderr=(
                "[AVFoundation indev @ 0x123] AVFoundation audio devices:\n"
                "[AVFoundation indev @ 0x123] [0] ZoomAudioDevice\n"
                "[AVFoundation indev @ 0x123] [1] MacBook Pro麦克风\n"
                "[AVFoundation indev @ 0x123] [2] DJI MIC MINI\n"
            ),
        )

        ffmpeg_input = resolve_ffmpeg_input(
            ffmpeg_input=":0",
            ffmpeg_input_name="DJI MIC MINI",
            run_command=lambda command: completed,
        )

        self.assertEqual(ffmpeg_input, ":2")

    def test_resolve_ffmpeg_input_matches_normalized_device_name(self):
        completed = subprocess.CompletedProcess(
            args=list_devices_command(),
            returncode=1,
            stdout="",
            stderr=(
                "[AVFoundation indev @ 0x123] AVFoundation audio devices:\n"
                "[AVFoundation indev @ 0x123] [0] ZoomAudioDevice\n"
                "[AVFoundation indev @ 0x123] [1] MacBook Pro麦克风\n"
                "[AVFoundation indev @ 0x123] [2] DJI MIC MINI\n"
            ),
        )

        ffmpeg_input = resolve_ffmpeg_input(
            ffmpeg_input=":0",
            ffmpeg_input_name="dji-mic",
            run_command=lambda command: completed,
        )

        self.assertEqual(ffmpeg_input, ":2")

    def test_resolve_ffmpeg_input_rejects_ambiguous_normalized_device_name(self):
        completed = subprocess.CompletedProcess(
            args=list_devices_command(),
            returncode=1,
            stdout="",
            stderr=(
                "[AVFoundation indev @ 0x123] AVFoundation audio devices:\n"
                "[AVFoundation indev @ 0x123] [0] DJI MIC MINI\n"
                "[AVFoundation indev @ 0x123] [1] DJI MIC MINI Backup\n"
            ),
        )

        with self.assertRaises(SystemExit) as raised:
            resolve_ffmpeg_input(
                ffmpeg_input=":0",
                ffmpeg_input_name="dji mic",
                run_command=lambda command: completed,
            )

        message = str(raised.exception)
        self.assertIn("ambiguous", message)
        self.assertIn("DJI MIC MINI", message)
        self.assertIn("DJI MIC MINI Backup", message)

    def test_resolve_ffmpeg_input_rejects_unknown_device_name(self):
        completed = subprocess.CompletedProcess(
            args=list_devices_command(),
            returncode=1,
            stdout="",
            stderr=(
                "[AVFoundation indev @ 0x123] AVFoundation audio devices:\n"
                "[AVFoundation indev @ 0x123] [0] ZoomAudioDevice\n"
                "[AVFoundation indev @ 0x123] [1] MacBook Pro麦克风\n"
            ),
        )

        with self.assertRaises(SystemExit) as raised:
            resolve_ffmpeg_input(
                ffmpeg_input=":0",
                ffmpeg_input_name="DJI MIC MINI",
                run_command=lambda command: completed,
            )

        self.assertIn("No audio device matched", str(raised.exception))
        self.assertIn("MacBook Pro麦克风", str(raised.exception))

    def test_makefile_exposes_record_devices_target(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("record-devices:", makefile)
        self.assertIn("bench/scripts/record_samples.py --list-devices", makefile)
        self.assertIn("$${EXPECT_DEVICE_NAME:+--expect-device-name", makefile)

    def test_makefile_exposes_record_preview_target(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("record-preview:", makefile)
        self.assertIn("--limit $${LIMIT:-1}", makefile)
        self.assertIn("--preview-asr", makefile)

    def test_makefile_exposes_record_check_target(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("record-check:", makefile)
        self.assertIn("--limit $${LIMIT:-1}", makefile)
        self.assertIn("--dry-run", makefile)

    def test_wav_duration_seconds_reads_valid_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            write_test_wav(audio, seconds=0.5)

            self.assertAlmostEqual(wav_duration_seconds(audio) or 0, 0.5)

    def test_missing_only_skips_existing_usable_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            write_test_wav(audio, seconds=0.5)

            self.assertFalse(should_record(1, audio, start_at=1, missing_only=True, min_duration=0.25))
            self.assertTrue(should_record(1, audio, start_at=1, missing_only=False, min_duration=0.25))

    def test_missing_only_rerecords_too_short_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            write_test_wav(audio, seconds=0.1)

            self.assertFalse(is_usable_audio(audio, min_duration=0.25))
            self.assertTrue(should_record(1, audio, start_at=1, missing_only=True, min_duration=0.25))

    def test_validate_recording_rejects_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "empty.wav"
            audio.write_bytes(b"")

            with self.assertRaises(SystemExit):
                validate_recording(audio, min_duration=0.25)

    def test_validate_recording_rejects_unreadable_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "broken.wav"
            audio.write_bytes(b"not a real wav")

            self.assertFalse(is_usable_audio(audio, min_duration=0.25))
            with self.assertRaises(SystemExit):
                validate_recording(audio, min_duration=0.25)

    def test_validate_recording_rejects_silent_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "silent.wav"
            write_test_wav(audio, seconds=0.25, signal=False)

            self.assertFalse(is_usable_audio(audio, min_duration=0.25))
            with self.assertRaises(SystemExit):
                validate_recording(audio, min_duration=0.25)

    def test_validate_recording_rejects_wrong_wav_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            wrong_rate = Path(tmp) / "wrong-rate.wav"
            stereo = Path(tmp) / "stereo.wav"
            write_test_wav(wrong_rate, seconds=0.25, rate=8000)
            write_test_wav(stereo, seconds=0.25, channels=2)

            self.assertFalse(is_usable_audio(wrong_rate, min_duration=0.25))
            self.assertFalse(is_usable_audio(stereo, min_duration=0.25))
            with self.assertRaises(SystemExit):
                validate_recording(wrong_rate, min_duration=0.25)
            with self.assertRaises(SystemExit):
                validate_recording(stereo, min_duration=0.25)

    def test_record_with_retries_accepts_second_valid_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            attempts = []
            prompts = []

            def fake_run(command, check):
                attempts.append((command, check))
                write_test_wav(audio, seconds=0.25, signal=len(attempts) > 1)

            with contextlib.redirect_stdout(io.StringIO()):
                duration = record_with_retries(
                    audio,
                    command=["record", str(audio)],
                    min_duration=0.25,
                    max_attempts=2,
                    wait_for_prompt=lambda prompt: prompts.append(prompt),
                    run_command=fake_run,
                )

            self.assertAlmostEqual(duration or 0, 0.25)
            self.assertEqual(len(attempts), 2)
            self.assertEqual(len(prompts), 2)

    def test_record_with_retries_fails_after_max_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            attempts = []

            def fake_run(command, check):
                attempts.append(command)
                write_test_wav(audio, seconds=0.25, signal=False)

            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    record_with_retries(
                        audio,
                        command=["record", str(audio)],
                        min_duration=0.25,
                        max_attempts=2,
                        wait_for_prompt=lambda prompt: None,
                        run_command=fake_run,
                    )

            self.assertEqual(len(attempts), 2)
            self.assertIn("silent", str(raised.exception))

    def test_record_with_retries_removes_rejected_file_before_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            file_existed_at_attempt_start = []

            def fake_run(command, check):
                file_existed_at_attempt_start.append(audio.exists())
                write_test_wav(audio, seconds=0.25, signal=len(file_existed_at_attempt_start) > 1)

            with contextlib.redirect_stdout(io.StringIO()):
                record_with_retries(
                    audio,
                    command=["record", str(audio)],
                    min_duration=0.25,
                    max_attempts=2,
                    wait_for_prompt=lambda prompt: None,
                    run_command=fake_run,
                )

            self.assertEqual(file_existed_at_attempt_start, [False, False])

    def test_record_with_retries_counts_down_before_recording(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            events = []

            def fake_run(command, check):
                events.append(("run", command, check))
                write_test_wav(audio, seconds=0.25)

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                record_with_retries(
                    audio,
                    command=["record", str(audio)],
                    min_duration=0.25,
                    max_attempts=1,
                    countdown_seconds=3,
                    wait_for_prompt=lambda prompt: events.append(("prompt", prompt)),
                    sleep=lambda seconds: events.append(("sleep", seconds)),
                    run_command=fake_run,
                )

            self.assertEqual(events[0][0], "prompt")
            self.assertEqual(events[1:4], [("sleep", 1), ("sleep", 1), ("sleep", 1)])
            self.assertEqual(events[4][0], "run")
            self.assertIn("录音将在 3 秒后开始", stdout.getvalue())

    def test_record_with_retries_reprints_reference_immediately_before_recording(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"

            def fake_run(command, check):
                write_test_wav(audio, seconds=0.25)

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                record_with_retries(
                    audio,
                    command=["record", str(audio)],
                    min_duration=0.25,
                    max_attempts=1,
                    wait_for_prompt=lambda prompt: None,
                    recording_text="帮我看一下 Codex 的 PR issue 有没有过 CI",
                    run_command=fake_run,
                )

            output = stdout.getvalue()
            self.assertIn("请读这句话", output)
            self.assertIn("帮我看一下 Codex 的 PR issue 有没有过 CI", output)

    def test_record_with_retries_uses_chinese_ready_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            prompts = []

            def fake_run(command, check):
                write_test_wav(audio, seconds=0.25)

            with contextlib.redirect_stdout(io.StringIO()):
                record_with_retries(
                    audio,
                    command=["record", str(audio)],
                    min_duration=0.25,
                    max_attempts=1,
                    wait_for_prompt=lambda prompt: prompts.append(prompt),
                    run_command=fake_run,
                )

            self.assertEqual(prompts, ["准备好后按回车。录音开始前会再显示一次要读的句子..."])

    def test_record_with_retries_retries_when_user_rejects_recording(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            attempts = []
            confirmations = iter(["n", "y"])

            def fake_run(command, check):
                attempts.append(command)
                write_test_wav(audio, seconds=0.25)

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                duration = record_with_retries(
                    audio,
                    command=["record", str(audio)],
                    min_duration=0.25,
                    max_attempts=2,
                    wait_for_prompt=lambda prompt: None,
                    confirm_recording=lambda prompt: next(confirmations),
                    run_command=fake_run,
                )

            self.assertAlmostEqual(duration or 0, 0.25)
            self.assertEqual(len(attempts), 2)
            self.assertTrue(audio.exists())
            self.assertIn("用户选择重录", stdout.getvalue())

    def test_record_with_retries_fails_when_user_rejects_last_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"

            def fake_run(command, check):
                write_test_wav(audio, seconds=0.25)

            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    record_with_retries(
                        audio,
                        command=["record", str(audio)],
                        min_duration=0.25,
                        max_attempts=1,
                        wait_for_prompt=lambda prompt: None,
                        confirm_recording=lambda prompt: "no",
                        run_command=fake_run,
                    )

            self.assertFalse(audio.exists())
            self.assertIn("用户选择重录", str(raised.exception))

    def test_record_with_retries_runs_preview_before_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            events = []

            def fake_run(command, check):
                events.append(("run", command))
                write_test_wav(audio, seconds=0.25)

            with contextlib.redirect_stdout(io.StringIO()):
                record_with_retries(
                    audio,
                    command=["record", str(audio)],
                    min_duration=0.25,
                    max_attempts=1,
                    wait_for_prompt=lambda prompt: events.append(("prompt", prompt)),
                    preview_recording=lambda path: events.append(("preview", path)),
                    confirm_recording=lambda prompt: events.append(("confirm", prompt)) or "y",
                    run_command=fake_run,
                )

            self.assertEqual([event[0] for event in events], ["prompt", "run", "preview", "confirm"])
            self.assertEqual(events[2], ("preview", audio))

    def test_sample_review_text_lists_reference_and_terms(self):
        text = sample_review_text(
            {
                "reference": "帮我看一下 Codex 的 PR issue 有没有过 CI",
                "terms": ["Codex", "PR", "issue", "CI"],
            }
        )

        self.assertIn("参考文本：帮我看一下 Codex 的 PR issue 有没有过 CI", text)
        self.assertIn("保护词：Codex, PR, issue, CI", text)

    def test_record_with_retries_prints_review_text_before_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            events = []

            def fake_run(command, check):
                write_test_wav(audio, seconds=0.25)

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                record_with_retries(
                    audio,
                    command=["record", str(audio)],
                    min_duration=0.25,
                    max_attempts=1,
                    wait_for_prompt=lambda prompt: None,
                    review_text="参考文本：Codex PR",
                    confirm_recording=lambda prompt: events.append(("confirm", prompt)) or "y",
                    run_command=fake_run,
                )

            self.assertEqual(events[0][0], "confirm")
            self.assertIn("参考文本：Codex PR", stdout.getvalue())

    def test_record_with_retries_uses_chinese_confirmation_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            prompts = []

            def fake_run(command, check):
                write_test_wav(audio, seconds=0.25)

            with contextlib.redirect_stdout(io.StringIO()):
                record_with_retries(
                    audio,
                    command=["record", str(audio)],
                    min_duration=0.25,
                    max_attempts=1,
                    wait_for_prompt=lambda prompt: None,
                    confirm_recording=lambda prompt: prompts.append(prompt) or "y",
                    run_command=fake_run,
                )

            self.assertEqual(prompts, ["保留这条录音吗？输入 y 保留，直接回车重录：[y/N] "])

    def test_whisper_preview_command_uses_resolved_asr_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "sample.wav"
            whisper_bin = root / "tools/whisper-cli"
            whisper_model = root / "models/ggml.bin"
            environment = {
                "SWITCHTYPE_WHISPER_BIN": str(whisper_bin),
                "SWITCHTYPE_WHISPER_MODEL": str(whisper_model),
                "SWITCHTYPE_WHISPER_NO_GPU": "1",
            }

            command = whisper_preview_command(audio, root=root, environment=environment)

            self.assertEqual(
                command,
                [
                    str(whisper_bin),
                    "-ng",
                    "-m",
                    str(whisper_model),
                    "-f",
                    str(audio),
                    "-l",
                    "auto",
                    "-nt",
                    "-np",
                ],
            )

    def test_selected_recordings_can_limit_missing_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recorded = root / "recorded.wav"
            write_test_wav(recorded, seconds=0.5)
            samples = [
                {"id": "sample-001", "audio": str(recorded)},
                {"id": "sample-002", "audio": str(root / "sample-002.wav")},
                {"id": "sample-003", "audio": str(root / "sample-003.wav")},
                {"id": "sample-004", "audio": str(root / "sample-004.wav")},
            ]

            selected = selected_recordings(
                samples,
                start_at=1,
                missing_only=True,
                min_duration=0.25,
                sample_id=None,
                limit=2,
            )

            self.assertEqual([index for index, _ in selected], [2, 3])
            self.assertEqual([sample["id"] for _, sample in selected], ["sample-002", "sample-003"])

    def test_selected_recordings_can_select_one_sample_id(self):
        samples = [
            {"id": "sample-001", "audio": "sample-001.wav"},
            {"id": "sample-002", "audio": "sample-002.wav"},
        ]

        selected = selected_recordings(
            samples,
            start_at=1,
            missing_only=False,
            min_duration=0.25,
            sample_id="sample-002",
            limit=None,
        )

        self.assertEqual([index for index, _ in selected], [2])

    def test_selected_recordings_rejects_unknown_sample_id(self):
        with self.assertRaises(SystemExit):
            selected_recordings(
                [{"id": "sample-001", "audio": "sample-001.wav"}],
                start_at=1,
                missing_only=False,
                min_duration=0.25,
                sample_id="sample-999",
                limit=None,
            )


if __name__ == "__main__":
    unittest.main()
