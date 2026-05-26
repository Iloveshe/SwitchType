# Security Policy

SwitchType handles microphone audio and generated transcripts locally. Security issues should be treated as high priority when they affect audio privacy, transcript handling, permission behavior, or command execution.

## Supported Versions

The project is pre-1.0. Security fixes target the current main branch.

## Reporting a Vulnerability

If this repository is public, report vulnerabilities through GitHub Security Advisories when available. If private, contact the repository owner directly.

Please include:

- Affected commit or release.
- Reproduction steps.
- Expected and actual behavior.
- Whether audio, transcripts, model paths, or shell command execution are involved.
- Any suggested fix, if known.

Do not include private audio samples or sensitive transcripts in public issues.

## Security Notes

- SwitchType does not use cloud ASR in v0.1.
- Temporary audio files are local and should be cleaned up after transcription.
- Local ASR command paths are user-configured; only use binaries you trust.
- The app requires Accessibility permission to observe the global hotkey and send paste events.
- Generated benchmark reports can contain transcript text. Review them before publishing.

