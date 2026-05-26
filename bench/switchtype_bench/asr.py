from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile


@dataclass(frozen=True)
class Transcription:
    text: str


class FakeEngine:
    def __init__(self, transcript: str):
        self.transcript = transcript

    def transcribe(self, audio: Path) -> Transcription:
        return Transcription(text=self.transcript)


class CommandEngine:
    def __init__(self, command: list[str], model: str | None, timeout_seconds: int):
        self.command = command
        self.model = model or ""
        self.timeout_seconds = timeout_seconds

    def transcribe(self, audio: Path) -> Transcription:
        if not audio.exists():
            raise FileNotFoundError(f"Audio file not found: {audio}")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "transcript.txt"
            output_without_suffix = output.with_suffix("")
            command = [
                part.format(
                    audio=str(audio),
                    output=str(output),
                    output_without_suffix=str(output_without_suffix),
                    model=self.model,
                )
                for part in self.command
            ]
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    self._diagnostic(
                        audio,
                        command,
                        f"command timed out after {self.timeout_seconds}s",
                        stdout=exc.stdout,
                        stderr=exc.stderr,
                    )
                ) from exc
            if completed.returncode != 0:
                if self._should_retry_with_cpu_fallback(completed, command):
                    self._remove_transcript_outputs(output, output_without_suffix)
                    fallback_command = self._cpu_fallback_command(command)
                    try:
                        completed = subprocess.run(
                            fallback_command,
                            check=False,
                            capture_output=True,
                            text=True,
                            timeout=self.timeout_seconds,
                        )
                    except subprocess.TimeoutExpired as exc:
                        raise RuntimeError(
                            self._diagnostic(
                                audio,
                                fallback_command,
                                f"CPU fallback command timed out after {self.timeout_seconds}s",
                                stdout=exc.stdout,
                                stderr=exc.stderr,
                            )
                        ) from exc
                    if completed.returncode == 0:
                        command = fallback_command
                    else:
                        raise RuntimeError(
                            self._diagnostic(
                                audio,
                                fallback_command,
                                (
                                    "Metal/GPU command failed; CPU fallback also failed "
                                    f"with exit code {completed.returncode}"
                                ),
                                stdout=completed.stdout,
                                stderr=completed.stderr,
                            )
                        )
                else:
                    raise RuntimeError(
                        self._diagnostic(
                            audio,
                            command,
                            f"command failed with exit code {completed.returncode}",
                            stdout=completed.stdout,
                            stderr=completed.stderr,
                        )
                    )
            transcript = ""
            if output.exists():
                transcript = output.read_text(encoding="utf-8").strip()
            else:
                whisper_output = output_without_suffix.with_suffix(".txt")
                if whisper_output.exists():
                    transcript = whisper_output.read_text(encoding="utf-8").strip()
                else:
                    transcript = completed.stdout.strip()
            if not transcript:
                diagnostics = "\n".join(
                    part.strip() for part in [completed.stderr, completed.stdout] if part.strip()
                )
                raise RuntimeError(
                    self._diagnostic(
                        audio,
                        command,
                        diagnostics or "Command engine produced an empty transcript.",
                    )
                )
            return Transcription(text=transcript)

    def _diagnostic(
        self,
        audio: Path,
        command: list[str],
        message: str,
        stdout: str | bytes | None = None,
        stderr: str | bytes | None = None,
    ) -> str:
        lines = [
            message.strip(),
            f"Audio: {audio}",
            "Command: " + " ".join(command),
        ]
        stderr_text = self._text(stderr).strip()
        stdout_text = self._text(stdout).strip()
        if stderr_text:
            lines.append(f"stderr: {stderr_text}")
        if stdout_text:
            lines.append(f"stdout: {stdout_text}")
        return "\n".join(lines)

    def _text(self, value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    def _should_retry_with_cpu_fallback(self, completed: subprocess.CompletedProcess[str], command: list[str]) -> bool:
        if "-ng" in command or "--no-gpu" in command:
            return False
        if not self._looks_like_whisper_command(command):
            return False
        return self._is_metal_initialization_failure(completed.stderr) or self._is_metal_initialization_failure(
            completed.stdout
        )

    def _looks_like_whisper_command(self, command: list[str]) -> bool:
        if not command:
            return False
        executable_name = Path(command[0]).name.lower()
        return "whisper" in executable_name or "-otxt" in command

    def _is_metal_initialization_failure(self, output: str | bytes | None) -> bool:
        text = self._text(output).lower()
        return (
            "ggml_metal_buffer_init" in text
            or "failed to allocate buffer" in text
            or ("metal" in text and "failed" in text)
        )

    def _cpu_fallback_command(self, command: list[str]) -> list[str]:
        return [command[0], "-ng", *command[1:]]

    def _remove_transcript_outputs(self, output: Path, output_without_suffix: Path) -> None:
        for candidate in [output, output_without_suffix.with_suffix(".txt")]:
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass
